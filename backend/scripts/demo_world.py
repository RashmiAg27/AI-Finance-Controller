"""The demo world's shape: accounts, import sources, and configured batches.

Kept apart from the seeding mechanics in seed_demo_world.py so the *content*
of the demo -- which is really a worked example of how an Indian
financial-services client's cash actually moves -- can be read on its own.

The structure to notice: each client has several bank accounts, and a batch
reconciles ONE of them. Two Bank<->GL cycles for the same client are not
redundant; they are HDFC and ICICI, which have different statement layouts,
different balances, and different breaks.
"""

CLIENTS = [
    {"code": "MRDN", "name": "Meridian Broking & Capital Services Pvt. Ltd."},
    {"code": "SHYD", "name": "Sahyadri Finserv Ltd."},
]

# (client_code, source_id) -> (file extension, sheet name for XLSX)
FILE_FORMATS = {
    ("MRDN", "internal_ledger"): ("xlsx", "Transactions"),
    ("MRDN", "bank_statement"): ("csv", None),
    ("MRDN", "icici_statement"): ("csv", None),
    ("MRDN", "treasury_ledger"): ("csv", None),
    ("MRDN", "exchange_obligation"): ("csv", None),
    ("SHYD", "internal_ledger"): ("csv", None),
    ("SHYD", "payment_gateway"): ("json", None),
    ("SHYD", "nach_return"): ("csv", None),
    ("SHYD", "bank_statement"): ("csv", None),
    ("SHYD", "tax_challan"): ("csv", None),
}

BANK_ACCOUNTS = {
    "MRDN": [
        {
            "account_code": "HDFC_OPERATING",
            "display_name": "HDFC Current — house operations",
            "bank_name": "HDFC Bank",
            "account_number_masked": "XXXXXXXX1234",
            "ifsc": "HDFC0000451",
            "branch": "Fort, Mumbai",
            "account_type": "CURRENT",
            "purpose": "OPERATING",
            "gl_code": "1101-HDFC-OPS",
        },
        {
            "account_code": "ICICI_OPERATING",
            "display_name": "ICICI Current — collections",
            "bank_name": "ICICI Bank",
            "account_number_masked": "XXXXXXXX5678",
            "ifsc": "ICIC0000112",
            "branch": "Bandra Kurla Complex, Mumbai",
            "account_type": "CURRENT",
            "purpose": "COLLECTIONS",
            "gl_code": "1102-ICICI-COLL",
        },
        {
            "account_code": "AXIS_SETTLEMENT",
            "display_name": "Axis — exchange settlement",
            "bank_name": "Axis Bank",
            "account_number_masked": "XXXXXXXX9012",
            "ifsc": "UTIB0000284",
            "branch": "Nariman Point, Mumbai",
            "account_type": "CURRENT",
            "purpose": "SETTLEMENT",
            "gl_code": "1103-AXIS-SETL",
        },
        {
            "account_code": "HDFC_CLIENT_FUNDS",
            "display_name": "HDFC — client funds (segregated)",
            "bank_name": "HDFC Bank",
            "account_number_masked": "XXXXXXXX3456",
            "ifsc": "HDFC0000451",
            "branch": "Fort, Mumbai",
            "account_type": "CURRENT",
            "purpose": "CLIENT_FUNDS",
            "gl_code": "1104-HDFC-CLIENT",
        },
    ],
    "SHYD": [
        {
            "account_code": "HDFC_COLLECTIONS",
            "display_name": "HDFC — EMI and aggregator collections",
            "bank_name": "HDFC Bank",
            "account_number_masked": "XXXXXXXX7788",
            "ifsc": "HDFC0000123",
            "branch": "Shivajinagar, Pune",
            "account_type": "CURRENT",
            "purpose": "COLLECTIONS",
            "gl_code": "2101-HDFC-COLL",
        },
        {
            "account_code": "ICICI_DISBURSAL",
            "display_name": "ICICI — loan disbursal",
            "bank_name": "ICICI Bank",
            "account_number_masked": "XXXXXXXX4455",
            "ifsc": "ICIC0004567",
            "branch": "Baner, Pune",
            "account_type": "CURRENT",
            "purpose": "DISBURSAL",
            "gl_code": "2102-ICICI-DISB",
        },
        {
            "account_code": "AXIS_TAX",
            "display_name": "Axis — statutory payments",
            "bank_name": "Axis Bank",
            "account_number_masked": "XXXXXXXX6611",
            "ifsc": "UTIB0000456",
            "branch": "Kalyani Nagar, Pune",
            "account_type": "CURRENT",
            "purpose": "TAX",
            "gl_code": "2103-AXIS-TAX",
        },
    ],
}

IMPORT_SOURCES = {
    "MRDN": [
        {
            "code": "MRDN_LOCAL_HDFC",
            "name": "HDFC statement drop (local directory)",
            "kind": "LOCAL_DIRECTORY",
            "connection": {
                "directory": "data/inbound/mrdn/hdfc",
                "file_pattern": "*.*",
                "notes": "Nightly pull from HDFC lands here before the 19:30 cutoff.",
            },
        },
        {
            "code": "MRDN_LOCAL_ICICI",
            "name": "ICICI statement drop (local directory)",
            "kind": "LOCAL_DIRECTORY",
            "connection": {
                "directory": "data/inbound/mrdn/icici",
                "file_pattern": "*.*",
                "notes": "ICICI uses a different layout entirely; the canonical mapping absorbs that.",
            },
        },
        {
            "code": "MRDN_SFTP_CLEARING",
            "name": "Exchange clearing corporation SFTP",
            "kind": "SFTP_CONNECTION",
            "connection": {
                "host": "sftp.clearing-corp.example",
                "port": 22,
                "username": "MRDN_CM_09112",
                "remote_path": "/outbound/obligations/cash",
                "key_reference": "vault://mrdn/clearing-sftp-ed25519",
                "file_pattern": "*.*",
            },
        },
        {
            "code": "MRDN_EMAIL_TREASURY",
            "name": "Treasury sweep confirmations mailbox",
            "kind": "EMAIL_INBOX",
            "connection": {
                "host": "imap.meridianbroking.example",
                "port": 993,
                "mailbox": "INBOX/Treasury/Sweeps",
                "username": "treasury-ops@meridianbroking.example",
                "sender_allowlist": ["confirmations@clearingbank.example"],
                "subject_pattern": "Own Account Transfer Confirmation*",
                "attachment_pattern": "*.*",
            },
        },
    ],
    "SHYD": [
        {
            "code": "SHYD_API_PG",
            "name": "Payment aggregator settlement API",
            "kind": "API_CONNECTION",
            "connection": {
                "base_url": "https://api.aggregator.example",
                "endpoint": "/v1/settlements/reconciliation",
                "auth_method": "HMAC_SHA256",
                "api_key_reference": "vault://shyd/aggregator-api-key",
                "poll_window_hours": 24,
            },
        },
        {
            "code": "SHYD_LOCAL_HDFC",
            "name": "HDFC collections statement drop",
            "kind": "LOCAL_DIRECTORY",
            "connection": {
                "directory": "data/inbound/shyd/hdfc",
                "file_pattern": "*.*",
            },
        },
        {
            "code": "SHYD_EMAIL_NACH",
            "name": "Sponsor bank NACH return mailbox",
            "kind": "EMAIL_INBOX",
            "connection": {
                "host": "imap.sahyadrifinserv.example",
                "port": 993,
                "mailbox": "INBOX/NACH",
                "username": "collections-recon@sahyadrifinserv.example",
                "sender_allowlist": ["nach.returns@sponsorbank.example"],
                "subject_pattern": "NACH Presentation Return File*",
                "attachment_pattern": "*.*",
            },
        },
        {
            "code": "SHYD_LOCAL_TAX",
            "name": "Tax challan export drop",
            "kind": "LOCAL_DIRECTORY",
            "connection": {
                "directory": "data/inbound/shyd/tax",
                "file_pattern": "*.*",
            },
        },
        {
            "code": "SHYD_LOCAL_DISBURSAL",
            "name": "Disbursal advice drop (local directory)",
            "kind": "LOCAL_DIRECTORY",
            "connection": {
                "directory": "data/inbound/shyd/disbursal",
                "file_pattern": "*.*",
                "notes": "Deliberately left empty -- repoint it from the Reconciliation window "
                         "and run the batch to see discovery work end to end.",
            },
        },
    ],
}

# Each entry is one configured batch. `reconciliation_type` says WHAT is being
# proved; `bank_account_code` says WHICH account it is proved for.
BATCH_DEFINITIONS = {
    "MRDN": [
        {
            "code": "MRDN_BANK_EOD_HDFC",
            "name": "Daily Bank Reconciliation — HDFC Operating",
            "description": "End-of-day proof that every movement on the HDFC operating account "
                           "has a matching entry in the OMS ledger, and vice versa.",
            "reconciliation_type": "BANK_GL",
            "bank_account_code": "HDFC_OPERATING",
            "batch_type": "DAILY_STATEMENT",
            "trigger_type": "SCHEDULED",
            "trigger_detail": "19:30 IST, Monday to Friday",
            "import_source_code": "MRDN_LOCAL_HDFC",
            "source_ids": ["internal_ledger", "bank_statement"],
            "cutoff_time": "19:30 IST",
            "sla_minutes": 45,
            "owner_team": "Treasury Operations",
        },
        {
            "code": "MRDN_BANK_EOD_ICICI",
            "name": "Daily Bank Reconciliation — ICICI Collections",
            "description": "The same proof for the ICICI account. A separate cycle because it is "
                           "a separate account with a separate balance and its own statement layout.",
            "reconciliation_type": "BANK_GL",
            "bank_account_code": "ICICI_OPERATING",
            "batch_type": "DAILY_STATEMENT",
            "trigger_type": "SCHEDULED",
            "trigger_detail": "19:45 IST, Monday to Friday",
            "import_source_code": "MRDN_LOCAL_ICICI",
            "source_ids": ["internal_ledger", "icici_statement"],
            "cutoff_time": "19:45 IST",
            "sla_minutes": 45,
            "owner_team": "Treasury Operations",
        },
        {
            "code": "MRDN_EXCH_OBLIGATION",
            "name": "Exchange Settlement Obligation — Axis",
            "description": "Reconciles booked exchange payouts against the clearing corporation's "
                           "net funds obligation, including brokerage and statutory charges.",
            "reconciliation_type": "EXCHANGE_CLEARING",
            "bank_account_code": "AXIS_SETTLEMENT",
            "batch_type": "SETTLEMENT_OBLIGATION",
            "trigger_type": "FILE_ARRIVAL",
            "trigger_detail": "On arrival of the CM segment obligation file",
            "import_source_code": "MRDN_SFTP_CLEARING",
            "source_ids": ["internal_ledger", "exchange_obligation"],
            "cutoff_time": "20:15 IST",
            "sla_minutes": 60,
            "owner_team": "Clearing & Settlement",
        },
        {
            "code": "MRDN_INTRADAY_SWEEP",
            "name": "Intraday Treasury Sweep",
            "description": "Proves both legs of every own-account sweep. Not scoped to one account "
                           "by design: the whole point is that it spans two.",
            "reconciliation_type": "INTERNAL_TRANSFER",
            "bank_account_code": None,
            "batch_type": "INTRADAY_SWEEP",
            "trigger_type": "SCHEDULED",
            "trigger_detail": "Every 2 hours, 09:00-17:00 IST",
            "import_source_code": "MRDN_EMAIL_TREASURY",
            "source_ids": ["treasury_ledger", "bank_statement", "icici_statement"],
            "cutoff_time": "17:00 IST",
            "sla_minutes": 30,
            "owner_team": "Treasury Operations",
        },
    ],
    "SHYD": [
        {
            "code": "SHYD_PG_SETTLEMENT",
            "name": "Payments ↔ Aggregator Settlement",
            "description": "Proves the aggregator's settlement against the individual collections "
                           "it contains, net of MDR, GST on MDR, commission and TDS.",
            "reconciliation_type": "PAYMENT_SETTLEMENT",
            "bank_account_code": None,
            "batch_type": "SETTLEMENT_OBLIGATION",
            "trigger_type": "SCHEDULED",
            "trigger_detail": "06:00 IST daily",
            "import_source_code": "SHYD_API_PG",
            "source_ids": ["internal_ledger", "payment_gateway"],
            "cutoff_time": "06:00 IST",
            "sla_minutes": 90,
            "owner_team": "Collections Operations",
        },
        {
            "code": "SHYD_SETTLEMENT_BANK",
            "name": "Settlement ↔ Bank Credit — HDFC",
            "description": "A separate proof over the same money: that the net the aggregator "
                           "reported actually arrived, tied by settlement UTR rather than amount.",
            "reconciliation_type": "SETTLEMENT_BANK",
            "bank_account_code": "HDFC_COLLECTIONS",
            "batch_type": "DAILY_STATEMENT",
            "trigger_type": "SCHEDULED",
            "trigger_detail": "10:00 IST daily",
            "import_source_code": "SHYD_LOCAL_HDFC",
            "source_ids": ["internal_ledger", "bank_statement"],
            "cutoff_time": "10:00 IST",
            "sla_minutes": 60,
            "owner_team": "Collections Operations",
        },
        {
            "code": "SHYD_NACH_COLLECTION",
            "name": "NACH Mandate Collections — HDFC",
            "description": "Reconciles presented EMI collections against the sponsor bank's NACH "
                           "presentation and return file.",
            "reconciliation_type": "BANK_AR",
            "bank_account_code": "HDFC_COLLECTIONS",
            "batch_type": "COLLECTION_MANDATE",
            "trigger_type": "FILE_ARRIVAL",
            "trigger_detail": "On arrival of the sponsor bank return file",
            "import_source_code": "SHYD_EMAIL_NACH",
            "source_ids": ["internal_ledger", "nach_return"],
            "cutoff_time": "11:00 IST",
            "sla_minutes": 60,
            "owner_team": "Collections Operations",
        },
        {
            "code": "SHYD_TAX_PAYMENT",
            "name": "Tax Liability ↔ Challan — Axis",
            "description": "Proves each GST and TDS liability was discharged by a challan and a "
                           "matching bank debit. Keyed on the challan number, never the amount.",
            "reconciliation_type": "TAX_PAYMENT",
            "bank_account_code": "AXIS_TAX",
            "batch_type": "FEE_INVOICE",
            "trigger_type": "MANUAL",
            "trigger_detail": "Run after each statutory payment run",
            "import_source_code": "SHYD_LOCAL_TAX",
            "source_ids": ["internal_ledger", "tax_challan"],
            "cutoff_time": None,
            "sla_minutes": 120,
            "owner_team": "Finance & Tax",
        },
        {
            "code": "SHYD_DISBURSAL_ADVICE",
            "name": "Loan Disbursal Advice — ICICI",
            "description": "Manual cycle for disbursal advices. Its import directory is empty by "
                           "design -- repoint it and run to see discovery work end to end.",
            "reconciliation_type": "BANK_AP",
            "bank_account_code": "ICICI_DISBURSAL",
            "batch_type": "DAILY_STATEMENT",
            "trigger_type": "MANUAL",
            "trigger_detail": "Run on demand by the disbursal desk",
            "import_source_code": "SHYD_LOCAL_DISBURSAL",
            "source_ids": ["internal_ledger", "payment_gateway"],
            "cutoff_time": None,
            "sla_minutes": 120,
            "owner_team": "Lending Operations",
        },
    ],
}
