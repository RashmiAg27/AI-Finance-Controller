import './office/office2007.css';
import { AgentPanel } from './agent/AgentPanel';
import { DocumentTabs, Ribbon, StatusBar, TitleBar } from './app/Shell';
import { WorkspaceProvider, useWorkspace } from './app/WorkspaceContext';
import { BatchRunBlotter } from './blotters/BatchRunBlotter';
import { DataSourcesBlotter } from './blotters/DataSourcesBlotter';
import { ExceptionsBlotter } from './blotters/ExceptionsBlotter';
import { ForecastBlotter } from './blotters/ForecastBlotter';
import { MatchingRulesBlotter } from './blotters/MatchingRulesBlotter';
import { ReconciliationBlotter } from './blotters/ReconciliationBlotter';
import { TaxBlotter } from './blotters/TaxBlotter';

function StartPage() {
  const { clientsError, loadingClients, clients } = useWorkspace();
  return (
    <div className="blotter">
      <header className="blotter__header">
        <span className="blotter__title">AI Finance Controller</span>
        <span className="blotter__subtitle">
          Reconciliation, tax &amp; settlement, exceptions and cash visibility
        </span>
      </header>
      <div className="blotter__body">
        {clientsError && (
          <div className="callout callout--error">
            {clientsError}
            <br />
            Start it with{' '}
            <span className="mono">python -m uvicorn app.main:app --reload --port 8000</span> from{' '}
            <span className="mono">backend/</span>.
          </div>
        )}
        {loadingClients && <div className="muted"><span className="spinner" /> Loading clients…</div>}

        {!clientsError && !loadingClients && clients.length === 0 && (
          <div className="callout callout--warn">
            No clients are configured. Seed the demo world:{' '}
            <span className="mono">python scripts/seed_demo_world.py --run</span>
          </div>
        )}

        <div className="callout">
          Pick a window from the ribbon above. Each one asks which client you want, then opens as its
          own tab you can keep open alongside the others.
        </div>

        <div className="kpis">
          <div className="kpi" style={{ minWidth: 250 }}>
            <div className="kpi__label">Reconciliation</div>
            <div className="small">
              Every configured batch for a client: its state, what triggers it, where its files come
              from. Edit those settings, then run one batch or all of them and watch the run.
            </div>
          </div>
          <div className="kpi" style={{ minWidth: 250 }}>
            <div className="kpi__label">Tax &amp; Fees</div>
            <div className="small">
              The fee, tax, commission and statutory charge treatment applied to this client's
              settlements — editable, versioned, and applied for real on the next run.
            </div>
          </div>
          <div className="kpi" style={{ minWidth: 250 }}>
            <div className="kpi__label">Matching Rules</div>
            <div className="small">
              How each source's own column names map onto our canonical fields, which identifiers are
              declared equivalent and why, and the rules each pass uses.
            </div>
          </div>
          <div className="kpi" style={{ minWidth: 250 }}>
            <div className="kpi__label">Forecast &amp; Exceptions</div>
            <div className="small">
              Confirmed cash, money at risk, the short-term projection, and everything the
              deterministic passes could not resolve.
            </div>
          </div>
        </div>

        <div className="callout">
          The panel on the right operates the same system. Ask it to run a client's reconciliations
          and it will show you what it is about to run and wait for your answer before starting
          anything.
        </div>
      </div>
    </div>
  );
}

function BlotterHost() {
  const { activeBlotter } = useWorkspace();

  if (!activeBlotter) {
    return (
      <div className="blotter-host">
        <StartPage />
      </div>
    );
  }

  return (
    <div className="blotter-host">
      {activeBlotter.kind === 'recon' && <ReconciliationBlotter blotter={activeBlotter} />}
      {activeBlotter.kind === 'batch' && <BatchRunBlotter blotter={activeBlotter} />}
      {activeBlotter.kind === 'sources' && <DataSourcesBlotter blotter={activeBlotter} />}
      {activeBlotter.kind === 'tax' && <TaxBlotter blotter={activeBlotter} />}
      {activeBlotter.kind === 'matching' && <MatchingRulesBlotter blotter={activeBlotter} />}
      {activeBlotter.kind === 'forecast' && <ForecastBlotter blotter={activeBlotter} />}
      {activeBlotter.kind === 'exceptions' && <ExceptionsBlotter blotter={activeBlotter} />}
    </div>
  );
}

function Window() {
  return (
    <div className="window">
      <TitleBar />
      <Ribbon />
      <div className="workspace">
        <div className="docarea">
          <DocumentTabs />
          <BlotterHost />
        </div>
        <AgentPanel />
      </div>
      <StatusBar />
    </div>
  );
}

export default function App() {
  return (
    <WorkspaceProvider>
      <Window />
    </WorkspaceProvider>
  );
}
