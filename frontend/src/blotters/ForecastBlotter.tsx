import { api, ApiError } from '../api/client';
import { Icon } from '../components/Icon';
import { Grid, Kpi, Pane } from '../components/Office';
import { useLoader, useWorkspace, type Blotter } from '../app/WorkspaceContext';
import { formatMoney } from '../lib/format';
import type { BankAccount, CashForecast, CashPosition } from '../types';

/**
 * Reads the cash position the last closed batch computed, plus the projection
 * built from it. Both are retrieved, never recomputed here -- a forecast the
 * screen calculated for itself could disagree with the one the agent quotes.
 */
export function ForecastBlotter({ blotter }: { blotter: Blotter }) {
  const { revision, refresh, clientById } = useWorkspace();
  const clientId = blotter.clientId;
  const client = clientById(clientId);

  const accounts = useLoader<BankAccount[]>(() => api.bankAccounts(clientId), [clientId, revision]);

  const loaded = useLoader<{ position: CashPosition | null; forecast: CashForecast | null }>(
    async () => {
      const [position, forecast] = await Promise.all([
        api.cashPosition(clientId).catch((e) => {
          if (e instanceof ApiError && e.status === 404) return null;
          throw e;
        }),
        api.cashForecast(clientId).catch((e) => {
          if (e instanceof ApiError && e.status === 404) return null;
          throw e;
        }),
      ]);
      return { position, forecast };
    },
    [clientId, revision],
  );

  const position = loaded.data?.position ?? null;
  const forecast = loaded.data?.forecast ?? null;

  const bandWidth =
    forecast && Number(forecast.high_estimate) - Number(forecast.low_estimate);

  return (
    <div className="blotter">
      <header className="blotter__header">
        <Icon name="forecast" size={16} />
        <span className="blotter__title">Cash Position &amp; Forecast</span>
        <span className="blotter__subtitle">{client ? `${client.name} (${client.code})` : clientId}</span>
        <span className="blotter__spacer" />
        {position && <span className="small muted">as of {position.as_of}</span>}
      </header>

      <div className="toolbar">
        <span className="toolbar__spacer" />
        <button type="button" className="btn" onClick={refresh}>
          <Icon name="refresh" size={12} /> Refresh
        </button>
      </div>

      <div className="blotter__body">
        {loaded.error && <div className="callout callout--error">{loaded.error}</div>}
        {loaded.loading && !loaded.data && (
          <div className="muted">
            <span className="spinner" /> Loading cash position…
          </div>
        )}

        {loaded.data && !position && (
          <div className="callout callout--warn">
            No cash position has been computed for this client yet. It is produced at the end of a
            successful batch run — run a batch from the Reconciliation window first.
          </div>
        )}

        {position && (
          <>
            <div className="kpis">
              <Kpi
                label="Confirmed cash"
                value={formatMoney(position.confirmed_cash)}
                note="reconciled against external records"
              />
              <Kpi label="Pending" value={formatMoney(position.pending_cash)} note="not yet confirmed" />
              <Kpi label="Expected in" value={formatMoney(position.expected_inflows)} />
              <Kpi label="Expected out" value={formatMoney(position.expected_outflows)} />
              <Kpi
                label="Unreconciled"
                value={formatMoney(position.unreconciled_amount)}
                note="total at risk across open exceptions"
              />
            </div>

            <Pane
              title="Where the money is"
              hint="Reconciled net movement per account — a client-level total cannot answer this"
              flush
            >
              <Grid
                columns={[
                  { key: 'account', label: 'Account' },
                  { key: 'bank', label: 'Bank' },
                  { key: 'purpose', label: 'Purpose' },
                  { key: 'net', label: 'Reconciled net movement', numeric: true },
                ]}
                empty="No per-account movement recorded yet."
              >
                {Object.entries(position.detail?.by_bank_account ?? {}).map(([accountId, amount]) => {
                  const account = (accounts.data ?? []).find((a) => a.id === accountId);
                  return (
                    <tr key={accountId}>
                      <td className="mono">{account?.account_code ?? accountId.slice(0, 8)}</td>
                      <td>{account ? `${account.bank_name} ${account.account_number_masked}` : '—'}</td>
                      <td>{account?.purpose ?? '—'}</td>
                      <td className="num">{formatMoney(amount)}</td>
                    </tr>
                  );
                })}
              </Grid>
              {position.detail?.internal_transfer_volume &&
                Number(position.detail.internal_transfer_volume) > 0 && (
                  <div className="pane__body">
                    <div className="callout callout--warn" style={{ marginBottom: 0 }}>
                      <strong>
                        {formatMoney(position.detail.internal_transfer_volume)} of own-account sweeps
                        was reconciled and deliberately excluded from the total.
                      </strong>
                      <br />
                      {position.detail.internal_transfer_note}
                    </div>
                  </div>
                )}
            </Pane>

            <Pane title="What these figures mean">
              <div className="small">
                <p style={{ marginTop: 0 }}>
                  <strong>Confirmed cash</strong> counts only amounts matched against an external
                  record — a bank statement, an aggregator settlement, an exchange obligation. An
                  internal ledger entry on its own never counts as confirmed, however plausible it
                  looks.
                </p>
                <p style={{ marginBottom: 0 }}>
                  <strong>Unreconciled</strong> is the total amount sitting in open exceptions. It is
                  money whose status is genuinely unknown, not money known to be lost.
                </p>
              </div>
            </Pane>
          </>
        )}

        {forecast && (
          <Pane title={`${forecast.horizon_days}-day forecast`} hint={`horizon ends ${forecast.as_of}`}>
            <div className="kpis">
              <Kpi label="Expected" value={formatMoney(forecast.expected_value)} />
              <Kpi label="Low" value={formatMoney(forecast.low_estimate)} />
              <Kpi label="High" value={formatMoney(forecast.high_estimate)} />
              <Kpi
                label="Band width"
                value={formatMoney(bandWidth ?? null)}
                note="driven by unreconciled amount"
              />
            </div>

            {forecast.drivers && (
              <Grid columns={[{ key: 'driver', label: 'Driver' }, { key: 'value', label: 'Value', numeric: true }]}>
                {Object.entries(forecast.drivers).map(([key, value]) => (
                  <tr key={key}>
                    <td>{key.replace(/_/g, ' ')}</td>
                    <td className="num">
                      {typeof value === 'number' || /^-?\d+(\.\d+)?$/.test(String(value))
                        ? formatMoney(String(value))
                        : String(value)}
                    </td>
                  </tr>
                ))}
              </Grid>
            )}

            {forecast.assumptions_note && (
              <div className="callout callout--warn" style={{ marginTop: 9 }}>
                <strong>Assumptions.</strong> {forecast.assumptions_note}
              </div>
            )}
          </Pane>
        )}
      </div>
    </div>
  );
}
