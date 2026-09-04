"""Pydantic contract for a client's versioned YAML configuration.

This is the one place client-specific facts are allowed to live. Nothing in
`app/domains/*` may hardcode a client's identifier names, field names, date
formats, or matching thresholds -- it all flows through this schema.

Reserved sections (`tax_fee_rules`, `ml_rules`, `settlement_rules`,
`cash_forecast_rules`) are declared as Optional now so that a config snapshot
written before a later milestone adds real content to them still validates
unchanged -- adding to them is additive, never a breaking schema change.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

CanonicalField = Literal[
    "transaction_date", "value_date", "settlement_date", "amount", "debit_credit",
    "counterparty", "account", "description", "identifier", "status",
    # A settlement report states its own gross/net decomposition; a bank
    # statement never does. Mapping these lets the engine explain a gap from
    # the source's own figures instead of re-deriving it from configured rates.
    "fee_amount", "tax_amount", "adjustment_amount",
    # How the money moved and who was on the other side. counterparty_type is
    # what marks a sweep between the client's own accounts as internal.
    "payment_method", "counterparty_type", "counterparty_account",
]


class FieldMapping(BaseModel):
    model_config = {"extra": "forbid"}

    source_field: str
    canonical_field: CanonicalField
    identifier_type: str | None = None  # required when canonical_field == "identifier"
    data_type: Literal["string", "date", "decimal"] = "string"
    date_format: str | None = None
    sign_convention: Literal["debit_negative", "credit_positive", "signed"] | None = None
    value_map: dict[str, str] | None = None
    required: bool = False

    @model_validator(mode="after")
    def _identifier_type_required(self) -> "FieldMapping":
        if self.canonical_field == "identifier" and not self.identifier_type:
            raise ValueError(f"field_mapping for source_field={self.source_field!r} maps to 'identifier' "
                              "but is missing identifier_type")
        if self.canonical_field in ("transaction_date", "value_date", "settlement_date") and self.data_type != "date":
            raise ValueError(f"field_mapping for {self.source_field!r} targets a date field but data_type "
                              f"is {self.data_type!r}, not 'date'")
        return self


class DataSourceConfig(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str
    role: Literal["INTERNAL", "EXTERNAL"]
    file_format: Literal["CSV", "XLSX", "JSON", "PDF"]
    sheet_name: str | None = None
    is_required: bool = True
    field_mappings: list[FieldMapping]
    identifier_priority: list[str] = Field(default_factory=list)
    static_fields: dict[str, str] = Field(default_factory=dict)


class IdentifierLinkageRule(BaseModel):
    """Explicit, client-authored statement that two identifier types refer to
    the same economic reference. Two identifiers are NEVER treated as
    equivalent by the matching engine merely because they are both configured
    identifier types -- only a rule here can establish that (spec correction:
    a UTR is not inherently a Trade ID)."""

    model_config = {"extra": "forbid"}

    rule_id: str | None = None
    source_identifier_type: str
    target_identifier_type: str
    linkage_type: Literal["DIRECT_EQUIVALENT", "DERIVED", "REQUIRES_LOOKUP"]
    transform: Literal["none", "strip_prefix", "regex_extract", "suffix_n"] = "none"
    transform_params: dict[str, str] | None = None
    confidence: float = 1.0
    rationale: str

    @model_validator(mode="after")
    def _default_rule_id(self) -> "IdentifierLinkageRule":
        if not self.rule_id:
            self.rule_id = f"LINK_{self.source_identifier_type}_TO_{self.target_identifier_type}"
        return self


class StringNormalizationRule(BaseModel):
    model_config = {"extra": "forbid"}

    field: str
    operations: list[Literal["trim", "uppercase", "lowercase", "collapse_whitespace"]]


class IdentifierNormalizationRule(BaseModel):
    model_config = {"extra": "forbid"}

    identifier_type: str
    operations: list[Literal["trim", "uppercase", "lowercase", "strip_non_alphanumeric"]]


class AmountNormalizationRule(BaseModel):
    model_config = {"extra": "forbid"}

    decimal_places: int = 2
    rounding: Literal["HALF_UP", "HALF_EVEN"] = "HALF_UP"


class NormalizationRules(BaseModel):
    model_config = {"extra": "forbid"}

    string_rules: list[StringNormalizationRule] = Field(default_factory=list)
    identifier_rules: list[IdentifierNormalizationRule] = Field(default_factory=list)
    amount_rules: AmountNormalizationRule = Field(default_factory=AmountNormalizationRule)


class ClassificationRule(BaseModel):
    model_config = {"extra": "forbid"}

    when: dict | None = None  # e.g. {"any_field_contains": "NEFT"}
    default: bool = False
    set: dict[str, str]

    @model_validator(mode="after")
    def _when_or_default(self) -> "ClassificationRule":
        if not self.default and not self.when:
            raise ValueError("classification_rules entries must set either 'when' or 'default: true'")
        return self


class MatchOnCondition(BaseModel):
    model_config = {"extra": "forbid"}

    left_identifier: str
    right_identifier: str
    comparison: Literal["exact", "normalized_partial"] = "exact"


class AmountTolerance(BaseModel):
    model_config = {"extra": "forbid"}

    type: Literal["absolute", "percentage"] = "absolute"
    value: float = 0.0


class MatchingRuleConditions(BaseModel):
    model_config = {"extra": "forbid"}

    amount_tolerance: AmountTolerance = Field(default_factory=AmountTolerance)
    date_field: Literal["transaction_date", "value_date", "settlement_date"] = "transaction_date"
    date_tolerance_days: int = 1
    counterparty_similarity_threshold: float | None = None
    instrument_type_match: Literal["exact", "any"] = "any"


class MatchingRule(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True}

    rule_id: str
    pass_number: int = Field(alias="pass")
    version: int = 1
    match_on: list[MatchOnCondition] = Field(default_factory=list)
    conditions: MatchingRuleConditions | None = None
    confidence: float


class ToleranceDefaults(BaseModel):
    model_config = {"extra": "forbid"}

    amount_tolerance: AmountTolerance = Field(default_factory=AmountTolerance)
    date_tolerance_days: int = 1


class ExceptionRules(BaseModel):
    model_config = {"extra": "forbid"}

    ageing_thresholds_days: dict[str, int] = Field(
        default_factory=lambda: {"LOW": 3, "MEDIUM": 7, "HIGH": 15, "CRITICAL": 30}
    )


class TaxFeeApplicability(BaseModel):
    model_config = {"extra": "forbid"}

    internal_instrument_type: str
    external_instrument_type: str


class FeeRuleConfig(BaseModel):
    """A commercial fee (e.g. payment-gateway MDR) is NOT a tax/regulatory
    figure -- it is negotiated per merchant agreement. verification_status
    must say so honestly rather than implying it was sourced the way the
    tax_on_fee rule is."""

    model_config = {"extra": "forbid"}

    rate_percent: float
    verification_status: Literal["VERIFIED", "NOT_VERIFIED", "PROTOTYPE_ASSUMPTION"]
    note: str | None = None


class TaxOnFeeConfig(BaseModel):
    model_config = {"extra": "forbid"}

    tax_rule_id: str


class CommissionRuleConfig(BaseModel):
    """Brokerage/commission the client itself charges or is charged on the
    gross amount. Commercial, not statutory -- same honesty requirement as
    FeeRuleConfig about where the number came from."""

    model_config = {"extra": "forbid"}

    label: str = "Commission"
    rate_percent: float = 0.0
    minimum_amount: float = 0.0
    maximum_amount: float | None = None
    verification_status: Literal["VERIFIED", "NOT_VERIFIED", "PROTOTYPE_ASSUMPTION"] = "PROTOTYPE_ASSUMPTION"
    note: str | None = None


class StatutoryChargeConfig(BaseModel):
    """One levy deducted alongside the fee -- STT, stamp duty, a SEBI turnover
    fee, an exchange transaction charge, TDS. `basis` says what the rate is
    applied to, so a charge on turnover is never silently computed on the fee.

    A charge carrying a real rate must say where that rate came from:
    source_authority/source_reference are how the agent can answer "why was
    this deducted?" without inventing a citation.
    """

    model_config = {"extra": "forbid"}

    code: str
    label: str
    basis: Literal["GROSS", "FEE", "FEE_PLUS_TAX"] = "GROSS"
    rate_percent: float = 0.0
    flat_amount: float = 0.0
    applies_to_instrument_types: list[str] = Field(default_factory=list)  # empty = every instrument
    enabled: bool = True
    source_authority: str | None = None
    source_reference: str | None = None
    verification_status: Literal["VERIFIED", "NOT_VERIFIED", "PROTOTYPE_ASSUMPTION"] = "NOT_VERIFIED"
    note: str | None = None


class AggregationRules(BaseModel):
    """Groups still-unmatched transactions on each side by a shared
    aggregation identifier (e.g. a settlement-batch reference) and matches
    the groups' amount sums -- this is how 1:N and N:1 relationships are
    represented, not by a special-cased 1:1 rule. The identifier_type here
    must be deliberately excluded from every Pass 1/2 matching_rules
    match_on condition so those passes don't consume the transactions before
    this pass can group them."""

    model_config = {"extra": "forbid"}

    identifier_type: str
    rule_id: str = "PASS6_AGGREGATION"
    amount_tolerance: AmountTolerance = Field(default_factory=AmountTolerance)
    date_field: Literal["transaction_date", "value_date", "settlement_date"] = "transaction_date"
    date_tolerance_days: int = 3
    confidence: float = 0.75


class TaxFeeRules(BaseModel):
    """Reserved section from M0, given real content in M3. A discrepancy
    between a gross internal amount and a net external amount is checked
    against this configuration *before* it is allowed to fall through to
    ML/exception handling (spec correction: tax/fee checking happens before
    the exception queue, not after)."""

    model_config = {"extra": "forbid"}

    applicable_when: TaxFeeApplicability
    fee: FeeRuleConfig
    tax_on_fee: TaxOnFeeConfig
    # Optional so a config written before commissions/statutory charges
    # existed still validates unchanged; an empty list means "none apply",
    # which is a different claim from "not configured".
    commission: Optional[CommissionRuleConfig] = None
    statutory_charges: list[StatutoryChargeConfig] = Field(default_factory=list)
    rounding_tolerance: float = 0.02
    date_field: Literal["transaction_date", "value_date", "settlement_date"] = "transaction_date"
    date_tolerance_days: int = 3
    confidence: float = 0.8


class ClientConfigSchema(BaseModel):
    model_config = {"extra": "forbid"}

    client_id: str
    config_version: int

    data_sources: list[DataSourceConfig]
    identifier_linkage: list[IdentifierLinkageRule] = Field(default_factory=list)
    normalization_rules: NormalizationRules = Field(default_factory=NormalizationRules)
    classification_rules: list[ClassificationRule] = Field(default_factory=list)
    matching_rules: list[MatchingRule] = Field(default_factory=list)
    tolerance_defaults: ToleranceDefaults = Field(default_factory=ToleranceDefaults)
    exception_rules: ExceptionRules = Field(default_factory=ExceptionRules)
    aggregation_rules: Optional[AggregationRules] = None

    # Reserved for later milestones -- present so old snapshots stay valid as
    # these gain real content. None means "not configured yet", not "empty".
    tax_fee_rules: Optional[TaxFeeRules] = None
    ml_rules: Optional[dict] = None
    settlement_rules: Optional[dict] = None
    cash_forecast_rules: Optional[dict] = None

    @model_validator(mode="after")
    def _at_least_one_internal_and_external_source(self) -> "ClientConfigSchema":
        roles = {ds.role for ds in self.data_sources}
        if "INTERNAL" not in roles or "EXTERNAL" not in roles:
            raise ValueError("data_sources must include at least one INTERNAL and one EXTERNAL source")
        return self

    @model_validator(mode="after")
    def _linkage_rules_reference_known_identifiers(self) -> "ClientConfigSchema":
        known_identifier_types: set[str] = set()
        for ds in self.data_sources:
            for fm in ds.field_mappings:
                if fm.canonical_field == "identifier" and fm.identifier_type:
                    known_identifier_types.add(fm.identifier_type)
        for rule in self.identifier_linkage:
            if rule.source_identifier_type not in known_identifier_types:
                raise ValueError(f"identifier_linkage references unknown source_identifier_type "
                                  f"{rule.source_identifier_type!r}")
            if rule.target_identifier_type not in known_identifier_types:
                raise ValueError(f"identifier_linkage references unknown target_identifier_type "
                                  f"{rule.target_identifier_type!r}")

        if self.aggregation_rules is not None:
            agg_type = self.aggregation_rules.identifier_type
            if agg_type not in known_identifier_types:
                raise ValueError(f"aggregation_rules.identifier_type {agg_type!r} is not a configured identifier")
            referenced_elsewhere = {
                cond.left_identifier for rule in self.matching_rules for cond in rule.match_on
            } | {
                cond.right_identifier for rule in self.matching_rules for cond in rule.match_on
            }
            if agg_type in referenced_elsewhere:
                raise ValueError(
                    f"aggregation_rules.identifier_type {agg_type!r} must not also be used in a "
                    "matching_rules.match_on condition -- Pass 1/2 would consume the transactions "
                    "before the aggregation pass can group them"
                )
        return self
