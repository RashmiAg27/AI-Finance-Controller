"""Anthropic tool-use JSON schemas, one per function in app.agent.tools.
Keep names/params in exact sync with TOOL_REGISTRY -- these are what the
model sees, not the Python signatures."""

TOOL_SCHEMAS = [
    {
        "name": "get_clients",
        "description": "List all clients visible in the current scope (id, code, name, status).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_client_configuration",
        "description": "Get a client's active configuration: data sources, identifier linkage rules, "
                        "matching rules, tax/fee rules, and aggregation rules. Use this to answer "
                        "questions about what identifiers/rules a client uses.",
        "input_schema": {
            "type": "object",
            "properties": {"client_id": {"type": "string"}},
            "required": ["client_id"],
        },
    },
    {
        "name": "get_batches",
        "description": "List batches, optionally filtered by client_id and/or status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "status": {"type": "string", "description": "e.g. CLOSED, FAILED, EXCEPTIONS_IDENTIFIED"},
            },
        },
    },
    {
        "name": "get_batch_status",
        "description": "Get a batch's full lifecycle status, timestamps, and reconciliation run stats.",
        "input_schema": {
            "type": "object",
            "properties": {"batch_id": {"type": "string"}},
            "required": ["batch_id"],
        },
    },
    {
        "name": "get_reconciliation_summary",
        "description": "THE tool for 'how did it go' / 'brief summary' / 'what is the coverage rate' "
                        "questions -- the backend's own canonical outcome for a batch: coverage_pct, "
                        "exception_count vs. affected_record_count vs. canonical_amount_at_risk (already "
                        "de-duplicated across paired exception rows -- never sum raw exception amounts "
                        "yourself), the top issues, and a compact cash snapshot. Call this first for a "
                        "summary question; call get_batch_report only once the user asks for full detail, "
                        "evidence, or to investigate a specific issue.",
        "input_schema": {
            "type": "object",
            "properties": {"batch_id": {"type": "string"}},
            "required": ["batch_id"],
        },
    },
    {
        "name": "get_transaction",
        "description": "Get full details for one transaction by its internal transaction_id, including "
                        "its identifiers and which match_id/exception_id (if any) it belongs to.",
        "input_schema": {
            "type": "object",
            "properties": {"transaction_id": {"type": "string"}},
            "required": ["transaction_id"],
        },
    },
    {
        "name": "find_transaction_by_reference",
        "description": "Find a transaction_id by a human-readable reference (canonical reference or any "
                        "identifier value like a UTR, order ID, or trade ID) within one client. Use this "
                        "first when a user names a transaction by reference rather than by transaction_id.",
        "input_schema": {
            "type": "object",
            "properties": {"client_id": {"type": "string"}, "reference": {"type": "string"}},
            "required": ["client_id", "reference"],
        },
    },
    {
        "name": "get_match_evidence",
        "description": "Get full evidence for a reconciliation match: rule_id, confidence, cardinality, "
                        "which transactions are involved (SOURCE/TARGET), and every comparison performed. "
                        "Use this to answer 'why was this matched' or 'which rule matched this'.",
        "input_schema": {
            "type": "object",
            "properties": {"match_id": {"type": "string"}},
            "required": ["match_id"],
        },
    },
    {
        "name": "get_exception",
        "description": "Get full details for one exception: type, severity, likely_cause, evidence, "
                        "and recommended_action.",
        "input_schema": {
            "type": "object",
            "properties": {"exception_id": {"type": "string"}},
            "required": ["exception_id"],
        },
    },
    {
        "name": "get_exception_summary",
        "description": "Get open-exception counts by type/severity and the largest exceptions by amount "
                        "impact for a batch. Use this for 'largest unresolved exceptions' style questions.",
        "input_schema": {
            "type": "object",
            "properties": {"batch_id": {"type": "string"}, "top_n": {"type": "integer"}},
            "required": ["batch_id"],
        },
    },
    {
        "name": "get_tax_rule",
        "description": "Get a tax rule's full definition: rate, applicability, effective period, source "
                        "authority/reference/URL, and verification_status (VERIFIED/NOT_VERIFIED/"
                        "PROTOTYPE_ASSUMPTION). Use this for any question about the regulatory basis of a tax figure.",
        "input_schema": {
            "type": "object",
            "properties": {"rule_id": {"type": "string"}},
            "required": ["rule_id"],
        },
    },
    {
        "name": "get_tax_calculation",
        "description": "Get the tax calculation (gross/fee/tax/net breakdown and the specific tax rule "
                        "applied) for a reconciliation match, if one was made via the fee/tax-explained pass.",
        "input_schema": {
            "type": "object",
            "properties": {"match_id": {"type": "string"}},
            "required": ["match_id"],
        },
    },
    {
        "name": "get_settlement",
        "description": "Get the settlement decomposition (gross -> fee -> tax -> net, and whether it is "
                        "fully explained) for a reconciliation match. Use this for 'why is the bank credit "
                        "lower than the gross amount' style questions.",
        "input_schema": {
            "type": "object",
            "properties": {"match_id": {"type": "string"}},
            "required": ["match_id"],
        },
    },
    {
        "name": "get_cash_position",
        "description": "Get a client's latest computed cash position: confirmed cash, pending cash, "
                        "expected inflows/outflows, and total unreconciled amount at risk.",
        "input_schema": {
            "type": "object",
            "properties": {"client_id": {"type": "string"}},
            "required": ["client_id"],
        },
    },
    {
        "name": "get_forecast",
        "description": "Get a client's latest short-term cash forecast, including its drivers and the "
                        "assumptions_note explaining this is a prototype heuristic, not a statistical model.",
        "input_schema": {
            "type": "object",
            "properties": {"client_id": {"type": "string"}},
            "required": ["client_id"],
        },
    },

    # -- Operations: configured batches, import sources, and running them ----
    {
        "name": "list_batch_definitions",
        "description": "List a client's CONFIGURED batches (the standing instructions shown in the "
                        "Reconciliation window) with their live state: AWAITING_DATA, DATA_AVAILABLE, "
                        "RUNNING, COMPLETED or FAILED, where their files come from, and how the last run "
                        "ended. Always call this before running anything, so you can name the batches to "
                        "the user and use real batch_definition_ids.",
        "input_schema": {
            "type": "object",
            "properties": {"client_id": {"type": "string"}},
            "required": ["client_id"],
        },
    },
    {
        "name": "get_import_sources",
        "description": "List a client's import sources (local directory, email inbox, SFTP or API "
                        "connection), their current connection settings and the result of the last poll.",
        "input_schema": {
            "type": "object",
            "properties": {"client_id": {"type": "string"}},
            "required": ["client_id"],
        },
    },
    {
        "name": "run_batch",
        "description": "Run ONE configured batch. This changes system state, so it refuses to act unless "
                        "confirmed=true: call it first with confirmed omitted to get the plan, put that "
                        "plan to the user, and only call again with confirmed=true after they agree. The "
                        "run executes in the background -- it is NOT finished when this returns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "batch_definition_id": {"type": "string",
                                         "description": "from list_batch_definitions"},
                "confirmed": {"type": "boolean",
                               "description": "true only after the user has explicitly agreed"},
            },
            "required": ["batch_definition_id"],
        },
    },
    {
        "name": "run_all_batches",
        "description": "Run every enabled configured batch for a client, or just the ones named in "
                        "batch_definition_codes. Like run_batch, it refuses until confirmed=true and "
                        "returns the plan first -- use that plan to ask the user whether they want all "
                        "batches or a specific one.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "batch_definition_codes": {
                    "type": "array", "items": {"type": "string"},
                    "description": "optional subset, e.g. ['MRDN_BANK_EOD']; omit to mean all enabled",
                },
                "confirmed": {"type": "boolean"},
            },
            "required": ["client_id"],
        },
    },
    {
        "name": "get_batch_log",
        "description": "Read a batch run's operator log: import/connection steps, per-stage progress, "
                        "every exception in full detail, and the error that stopped a failed run. This is "
                        "where the reason a batch failed actually lives -- read it before explaining a "
                        "failure. Pass level='ERROR' or level='EXCEPTION' to filter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "string"},
                "level": {"type": "string", "description": "INFO | WARN | ERROR | EXCEPTION"},
                "limit": {"type": "integer"},
            },
            "required": ["batch_id"],
        },
    },
    {
        "name": "get_batch_report",
        "description": "The FULL, detailed result of a finished run: every match, every exception with "
                        "its raw amount_impact and evidence, settlement decomposition, and the resulting "
                        "cash position and forecast. This is detail/investigation-mode data -- for a "
                        "summary question ('how did it go', 'brief'), call get_reconciliation_summary "
                        "instead; reach for this one only after the user asks for detail, evidence, or to "
                        "investigate a specific issue. Never sum this tool's raw amount_impact values "
                        "yourself for a total at risk -- that double-counts paired exception rows; use "
                        "get_reconciliation_summary's canonical_amount_at_risk for that.",
        "input_schema": {
            "type": "object",
            "properties": {"batch_id": {"type": "string"}},
            "required": ["batch_id"],
        },
    },
    # -- Analysis: accounts, reconciliation types, arithmetic ---------------
    {
        "name": "list_reconciliation_types",
        "description": "The catalogue of reconciliation types the platform performs (Bank<->GL, "
                        "Bank<->AR, Payments<->Settlement, Settlement<->Bank, internal transfer, "
                        "tax payment, TDS chain, chargeback, exchange clearing), each with the sides "
                        "it compares, its natural key, and WHICH DIFFERENCES ARE LEGITIMATE for it. "
                        "Consult this before calling a difference a break -- a gross sale not equalling "
                        "a net settlement is expected, not an error.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_bank_accounts",
        "description": "A client's bank accounts. These are the actual units of reconciliation: a "
                        "client holds several accounts at different banks, each with its own "
                        "statement and its own balance, and they are never pooled.",
        "input_schema": {
            "type": "object",
            "properties": {"client_id": {"type": "string"}},
            "required": ["client_id"],
        },
    },
    {
        "name": "get_account_position",
        "description": "Cash broken down per bank account, plus the internal-transfer volume that was "
                        "deliberately excluded from the total. Use this for 'where is the money' -- a "
                        "single client-level figure cannot answer it.",
        "input_schema": {
            "type": "object",
            "properties": {"client_id": {"type": "string"}},
            "required": ["client_id"],
        },
    },
    {
        "name": "explain_amount_difference",
        "description": "THE tool for 'why is the credit smaller than the invoice?'. Given a gross "
                        "figure and what actually arrived, it applies the client's own configured fee, "
                        "tax-on-fee, commission and statutory charges and returns the arithmetic LINE "
                        "BY LINE, plus the residual and whether the rules fully explain the gap. Show "
                        "the workings to the user; do not do this arithmetic yourself.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "gross_amount": {"type": "string", "description": "the booked/invoiced figure"},
                "observed_amount": {"type": "string", "description": "what actually arrived"},
                "instrument_type": {"type": "string",
                                     "description": "optional, decides which charges apply"},
            },
            "required": ["client_id", "gross_amount", "observed_amount"],
        },
    },
    {
        "name": "search_transactions",
        "description": "Find transactions by amount range, counterparty, payment method (UPI, NEFT, "
                        "RTGS, IMPS, NACH, CHEQUE, PAYMENT_GATEWAY, INTERNAL_TRANSFER, ...), source "
                        "feed, or bank account. Use for open-ended questions like 'show the largest "
                        "UPI credits' or 'what did we pay this vendor'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "min_amount": {"type": "string"},
                "max_amount": {"type": "string"},
                "counterparty": {"type": "string", "description": "partial match, case insensitive"},
                "payment_method": {"type": "string"},
                "source_id": {"type": "string"},
                "bank_account_id": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["client_id"],
        },
    },
    {
        "name": "aggregate_exceptions",
        "description": "Counts and money-at-risk for a client's open exceptions, grouped by "
                        "exception_type, severity, batch, or reconciliation_type. Use this for "
                        "'what is our biggest problem' rather than listing every exception.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "group_by": {"type": "string",
                              "description": "exception_type | severity | batch | reconciliation_type"},
            },
            "required": ["client_id"],
        },
    },
    {
        "name": "update_import_source",
        "description": "Change where a batch's files are fetched from (for example, point it at a "
                        "different local directory). Refuses until confirmed=true and returns the current "
                        "settings alongside the proposed change so the user can approve the exact diff. "
                        "After applying, it re-probes the connection and reports what it found.",
        "input_schema": {
            "type": "object",
            "properties": {
                "import_source_id": {"type": "string", "description": "from get_import_sources"},
                "connection": {"type": "object",
                                "description": "full replacement connection object for this kind, "
                                               "e.g. {'directory': 'C:/feeds/bank', 'file_pattern': '*.csv'}"},
                "kind": {"type": "string",
                          "description": "LOCAL_DIRECTORY | EMAIL_INBOX | SFTP_CONNECTION | API_CONNECTION"},
                "enabled": {"type": "boolean"},
                "confirmed": {"type": "boolean"},
            },
            "required": ["import_source_id"],
        },
    },
]
