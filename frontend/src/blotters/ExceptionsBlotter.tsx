import { useMemo, useState } from 'react';
import { api } from '../api/client';
import { Icon } from '../components/Icon';
import { Badge, Grid, Kpi, Pane } from '../components/Office';
import { useLoader, useWorkspace, type Blotter } from '../app/WorkspaceContext';
import { formatMoney } from '../lib/format';
import type { BatchReport, ExceptionItem } from '../types';

interface Row extends ExceptionItem {
  batchCode: string;
  batchId: string;
}

/**
 * The exception queue across every batch this client has run. Built by
 * reading each batch's own report rather than by a separate query, so a
 * number here is the same number the batch window shows.
 */
export function ExceptionsBlotter({ blotter }: { blotter: Blotter }) {
  const { revision, refresh, clientById, openBlotter } = useWorkspace();
  const clientId = blotter.clientId;
  const client = clientById(clientId);
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [typeFilter, setTypeFilter] = useState('ALL');

  const loaded = useLoader<BatchReport[]>(
    async () => {
      const definitions = await api.batchDefinitions(clientId);
      const batchIds = definitions
        .map((d) => d.latest_run?.id)
        .filter((id): id is string => Boolean(id));
      return Promise.all(batchIds.map((id) => api.batchReport(id)));
    },
    [clientId, revision],
  );

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = [];
    for (const report of loaded.data ?? []) {
      for (const item of report.exceptions.items) {
        out.push({ ...item, batchCode: report.batch.batch_code, batchId: report.batch.id });
      }
    }
    return out.sort((a, b) => Number(b.amount_impact ?? 0) - Number(a.amount_impact ?? 0));
  }, [loaded.data]);

  const severities = useMemo(() => [...new Set(rows.map((r) => r.severity))].sort(), [rows]);
  const types = useMemo(() => [...new Set(rows.map((r) => r.exception_type))].sort(), [rows]);

  const filtered = rows.filter(
    (row) =>
      (severityFilter === 'ALL' || row.severity === severityFilter) &&
      (typeFilter === 'ALL' || row.exception_type === typeFilter),
  );

  const openCount = filtered.filter((r) => r.status === 'OPEN').length;
  const atRisk = filtered
    .filter((r) => r.status === 'OPEN')
    .reduce((sum, r) => sum + Number(r.amount_impact ?? 0), 0);

  return (
    <div className="blotter">
      <header className="blotter__header">
        <Icon name="exception" size={16} />
        <span className="blotter__title">Exception Queue</span>
        <span className="blotter__subtitle">{client ? `${client.name} (${client.code})` : clientId}</span>
        <span className="blotter__spacer" />
        <span className="small muted">latest run of each configured batch</span>
      </header>

      <div className="toolbar">
        <label className="small">
          Severity{' '}
          <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
            <option value="ALL">All</option>
            {severities.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="small">
          Type{' '}
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
            <option value="ALL">All</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {t.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
        </label>
        <span className="toolbar__spacer" />
        <button type="button" className="btn" onClick={refresh}>
          <Icon name="refresh" size={12} /> Refresh
        </button>
      </div>

      <div className="blotter__body">
        {loaded.error && <div className="callout callout--error">{loaded.error}</div>}
        {loaded.loading && !loaded.data && (
          <div className="muted">
            <span className="spinner" /> Loading exceptions…
          </div>
        )}

        <div className="kpis">
          <Kpi label="Shown" value={filtered.length} note={`${rows.length} total`} />
          <Kpi label="Open" value={openCount} />
          <Kpi label="At risk" value={formatMoney(atRisk)} note="open exceptions only" />
        </div>

        <Pane title="Exceptions" hint={`${filtered.length} row(s)`} flush>
          <Grid
            columns={[
              { key: 'batch', label: 'Batch' },
              { key: 'type', label: 'Type' },
              { key: 'sev', label: 'Severity' },
              { key: 'status', label: 'Status' },
              { key: 'amount', label: 'Amount impact', numeric: true },
              { key: 'cause', label: 'Likely cause (system)' },
              { key: 'action', label: 'Recommended action' },
              { key: 'txns', label: 'Transactions' },
            ]}
            empty={
              loaded.loading
                ? 'Loading…'
                : 'No exceptions. Either nothing has been run yet, or every transaction resolved.'
            }
          >
            {filtered.map((row) => (
              <tr
                key={row.id}
                className="is-clickable"
                onDoubleClick={() =>
                  openBlotter({
                    kind: 'batch',
                    clientId,
                    batchId: row.batchId,
                    title: `Batch run — ${row.batchCode}`,
                    subtitle: row.batchCode,
                  })
                }
              >
                <td className="mono small">{row.batchCode}</td>
                <td className="nowrap">{row.exception_type.replace(/_/g, ' ')}</td>
                <td>
                  <Badge value={row.severity} />
                </td>
                <td>
                  <Badge value={row.status} />
                </td>
                <td className="num">{formatMoney(row.amount_impact)}</td>
                <td>{row.likely_cause ?? '—'}</td>
                <td>{row.recommended_action ?? '—'}</td>
                <td className="small">
                  {row.transactions.map((txn) => (
                    <div key={txn.transaction_id}>
                      <span className="mono">{txn.reference ?? txn.transaction_id.slice(0, 8)}</span>{' '}
                      {formatMoney(txn.amount)} · {txn.source_id}
                      {txn.counterparty ? ` · ${txn.counterparty}` : ''}
                    </div>
                  ))}
                </td>
              </tr>
            ))}
          </Grid>
        </Pane>

        <div className="callout">
          Double-click a row to open the batch run it came from, where the same exception appears in
          the run log with its full evidence.
        </div>
      </div>
    </div>
  );
}
