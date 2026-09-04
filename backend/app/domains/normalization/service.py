from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import IngestionError
from app.domains.classification.rules_engine import classify
from app.domains.normalization.field_mapper import map_record
from app.domains.normalization.identifier_mapper import resolve_identifiers
from app.models.batch import Batch, BatchFile
from app.models.batch_definition import BatchDefinition
from app.models.config_version import ClientConfiguration
from app.models.data_source import DataSource
from app.models.source_file import SourceFile, SourceRecord
from app.models.transaction import Transaction, TransactionIdentifier
from app.schemas.config import ClientConfigSchema


def _batch_bank_account_id(db: Session, batch: Batch) -> str | None:
    if not batch.batch_definition_id:
        return None
    definition = db.get(BatchDefinition, batch.batch_definition_id)
    return definition.bank_account_id if definition else None


def normalize_batch(db: Session, batch: Batch) -> list[Transaction]:
    """Turns every OK SourceRecord belonging to this batch into a canonical
    Transaction (+ its TransactionIdentifiers), using the config version bound
    to the batch at creation time -- never "whatever is ACTIVE now"."""
    config_row = db.get(ClientConfiguration, batch.config_version_id)
    config = ClientConfigSchema.model_validate(config_row.parsed_json)
    ds_config_by_source_id = {ds.source_id: ds for ds in config.data_sources}

    batch_files = list(db.execute(select(BatchFile).where(BatchFile.batch_id == batch.id)).scalars())
    transactions: list[Transaction] = []

    # Every transaction a batch produces belongs to the account that batch
    # reconciles, when it has one. That is what keeps an HDFC break from being
    # netted against an ICICI movement later.
    bank_account_id = _batch_bank_account_id(db, batch)

    for bf in batch_files:
        source_file = db.get(SourceFile, bf.source_file_id)
        data_source = db.get(DataSource, bf.data_source_id)
        ds_config = ds_config_by_source_id.get(data_source.source_id)
        if ds_config is None:
            raise IngestionError(f"no field_mappings configured for data source {data_source.source_id!r}")

        records = list(
            db.execute(
                select(SourceRecord)
                .where(SourceRecord.source_file_id == source_file.id, SourceRecord.parse_status == "OK")
                .order_by(SourceRecord.row_number)
            ).scalars()
        )

        for record in records:
            row_context = f"{data_source.source_id} row {record.row_number}"
            mapped = map_record(record.raw_data, ds_config, row_context=row_context)

            if mapped.transaction_date is None:
                raise IngestionError(f"{row_context}: transaction_date could not be resolved")
            if mapped.amount is None:
                raise IngestionError(f"{row_context}: amount could not be resolved")

            debit_credit = mapped.debit_credit or ("DEBIT" if mapped.amount < 0 else "CREDIT")

            identifiers, canonical_reference = resolve_identifiers(mapped.identifiers, ds_config, config)
            attributes = classify(mapped, config.classification_rules, data_source.source_id)

            # Evaluation-only passthrough: if the raw row carries a
            # ground-truth tag (synthetic data / tests only -- no real client
            # file has this column, and no field_mapping ever declares it),
            # copy it into metadata_json. No matching/tax/ML pass reads this.
            metadata: dict = {}
            eco_id = record.raw_data.get("_ground_truth_economic_id")
            if eco_id:
                metadata["economic_transaction_id"] = eco_id

            txn = Transaction(
                client_id=batch.client_id,
                batch_id=batch.id,
                source_id=data_source.source_id,
                source_record_id=record.id,
                canonical_reference=canonical_reference,
                bank_account_id=bank_account_id,
                transaction_type=attributes["transaction_type"],
                instrument_type=attributes["instrument_type"],
                payment_method=attributes.get("payment_method"),
                transaction_date=mapped.transaction_date,
                value_date=mapped.value_date,
                settlement_date=mapped.settlement_date,
                amount=abs(mapped.amount),
                currency=mapped.static_fields.get("currency", "INR"),
                debit_credit=debit_credit,
                fee_amount=mapped.fee_amount,
                tax_amount=mapped.tax_amount,
                adjustment_amount=mapped.adjustment_amount,
                counterparty=mapped.counterparty,
                counterparty_type=attributes.get("counterparty_type", "UNKNOWN"),
                counterparty_account=mapped.counterparty_account,
                account=mapped.account,
                description=mapped.description,
                status="POSTED",
                source_system=mapped.static_fields.get("source_system", data_source.source_id),
                metadata_json=metadata,
            )
            db.add(txn)
            db.flush()

            for ident in identifiers:
                db.add(TransactionIdentifier(
                    transaction_id=txn.id,
                    client_id=batch.client_id,
                    identifier_type=ident.identifier_type,
                    value_raw=ident.value_raw,
                    value_normalized=ident.value_normalized,
                    is_primary=ident.is_primary,
                    linked_via_rule_id=ident.linked_via_rule_id,
                ))
            transactions.append(txn)

    db.flush()
    return transactions
