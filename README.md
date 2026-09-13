live- https://ai-finance-controller-1-7rrg.onrender.com/
# AI Finance Controller

A multi-client reconciliation, tax/settlement, exception-management and
cash-visibility platform, operated through an Office-2007-style workspace with
an AI controller docked in the right-hand panel.

The UI is deliberately plain and light: a ribbon, document tabs, dense grids,
no theming. It is an operations tool, and an analyst wants twenty batch rows on
screen rather than six.

## What is in it

**Four windows, opened from the ribbon.** Each asks which client you want and
then opens as its own tab, so you can keep a client's batches, its tax rules
and a running batch open side by side.

| Window | What it does |
| --- | --- |
| **Reconciliation** | Every *configured* batch for a client — its state, what triggers it, which data sources it needs and where its files come from. Edit those settings, then run one batch or all of them and watch the run advance. |
| **Tax & Fees** | The fee, tax-on-fee, commission and statutory-charge treatment applied to this client's settlements. Editable, versioned, and genuinely applied on the next run. |
| **Matching Rules** | How each source's own column names map onto the canonical fields, which identifier types are declared equivalent and *why*, and the rules each deterministic pass uses. |
| **Forecast / Exceptions** | Confirmed cash, money at risk, the short-term projection, and everything the deterministic passes could not resolve. |

**Configured batches, not ad-hoc runs.** A `BatchDefinition` is the standing
instruction ("reconcile Meridian's bank statement against the OMS ledger every
evening at 19:30, files arrive in this directory"); each execution creates a
`Batch`. Editing a definition affects the next run, never one in flight — a
batch binds its configuration version when it is created.

**Import sources that actually fetch.** `LOCAL_DIRECTORY` reads this machine's
filesystem for real: point a batch at a folder, save, run, and it picks up
whatever is sitting there. `EMAIL_INBOX`, `SFTP_CONNECTION` and
`API_CONNECTION` are simulated against a per-connection staging area under
`data/simulated/`, and their logs narrate the protocol steps a real connector
would perform. Files are routed to a data source by name:
`<source_id>__<anything>.<ext>`.

**A run log that explains itself.** Import discovery, per-stage progress, every
exception in full (type, severity, money at risk, the system's own likely cause
and recommended action), and the error that stopped a failed run — all in one
place, so a failure can be diagnosed without cross-referencing four tables.

**An agent that operates the system.** The panel on the right can list what is
configured, run a batch or all of them, repoint an import source, read back a
finished run, and explain a failure by quoting the log. Every state-changing
tool refuses to act until it is called with `confirmed=true` and returns the
plan it *would* execute — that gate lives in the tool, not in the prompt, so a
model that ignored its instructions still could not start a run without you
agreeing first.

**Honesty about rates.** Every fee, commission and statutory charge carries a
`verification_status` that the UI renders. Exactly one tax rate in the system is
`VERIFIED` against a primary source; the rest say `NOT_VERIFIED` or
`PROTOTYPE_ASSUMPTION` and mean it. See [docs/tax-rules.md](docs/tax-rules.md).

## The demo world

Two fabricated clients, inspired by Indian financial enterprises:

- **MRDN — Meridian Broking & Capital Services Pvt. Ltd.** (Mumbai broker-dealer)
  reconciles its OMS ledger against a clearing bank statement and an exchange
  clearing-corporation obligation file. Three batches: a scheduled end-of-day
  bank cycle (local directory), a file-arrival-triggered exchange settlement
  cycle (SFTP), and a two-hourly intraday sweep (emailed statements).
- **SHYD — Sahyadri Finserv Ltd.** (Pune NBFC) reconciles its collections ledger
  against a payment aggregator's settlement feed (API) and the sponsor bank's
  NACH presentation/return file (emailed attachment). A third batch, loan
  disbursal advice, is deliberately left with an empty import directory so you
  can repoint it and watch discovery work end to end.

The fabricated data carries realistic fields — UTRs, IFSC codes, UMRNs, cheque
references, clearing-member codes, NPCI return reasons, settlement numbers — and
produces genuine outcomes: exact and normalized reference matches, amount/date
matches, 1:N split settlements, fee-and-charge-explained settlements, duplicates,
missing records on either side, and unexplained variances.

## Running it

### 1. Backend

```bash
cd backend
python -m venv .venv
./.venv/Scripts/pip install -e ".[dev]"    # Windows; use .venv/bin on macOS/Linux
cp .env.example .env                        # add GEMINI_API_KEY or ANTHROPIC_API_KEY to enable the agent
```

Build the demo world — clients, configurations, import sources, configured
batches, and the feed files waiting in each one:

```bash
./.venv/Scripts/python scripts/seed_demo_world.py --run
```

Drop `--run` to leave every batch un-run, so you can start them yourself from
the UI or by asking the agent.

Start the API:

```bash
./.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Run tests:

```bash
./.venv/Scripts/python -m pytest tests/
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173, expects the API at http://localhost:8000/api/v1
```

Set `VITE_API_BASE_URL` in `frontend/.env` if the backend runs elsewhere.

### Useful knobs

- `BATCH_STAGE_DELAY_SECONDS` (default `0.45`) — the deliberate pause between
  pipeline stages so a run is observable in the UI. Set to `0` for benchmarking.

## Try this

1. Ribbon → **Reconciliation** → pick **Meridian**. You get its three configured
   batches, their state, triggers and import locations.
2. Select **SHYD_DISBURSAL_ADVICE** (Sahyadri) — it is `AWAITING_DATA`. Click
   **Edit import source**, point it at a folder containing
   `internal_ledger__2026-09-02.csv` and `payment_gateway__2026-09-02.json`
   (copy them from `data/simulated/api_connection/SHYD/SHYD_API_PG/`), then
   **Save & test connection**. Run it and watch the stages advance.
3. Open the batch and read its log — including every exception with its evidence.
4. Ribbon → **Tax & Fees** → change a rate → **Save**. It becomes a new
   configuration version and changes which settlements reconcile next run.
5. Ask the agent (with an API key set): *"run the reconciliations for this
   client"*. It lists what it would run and waits for your answer.

## Repository layout

```
backend/    FastAPI app: domain services, AI agent, API
  app/domains/     config, ingestion, normalization, reconciliation (6 passes),
                   tax, settlement, exceptions, cash, forecasting, batches
  configs/clients/ per-client YAML configuration (MRDN, SHYD + test fixtures)
  scripts/         seed_demo_world.py, evaluate_against_ground_truth.py
frontend/   React + TypeScript + Vite; Office 2007 workspace
data/       feed landing areas + raw/parsed storage, never committed
docs/       architecture and tax-rule provenance
```

## Status

The deterministic pipeline, the configuration/orchestration layer, the four
operator windows and the agent are built and tested (26 backend tests).
ML-assisted ranking (Pass 7) is intentionally deferred until last, per the
approved plan.
