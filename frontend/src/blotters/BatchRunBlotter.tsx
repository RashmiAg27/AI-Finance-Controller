import { useState } from 'react';
import { api } from '../api/client';
import { Icon } from '../components/Icon';
import { Badge, Grid, Kpi, Pane, Progress } from '../components/Office';
import { useLoader, useWorkspace, type Blotter } from '../app/WorkspaceContext';
import { DEFAULT_DISPLAY_TIMEZONE, formatMoney, formatTime } from '../lib/format';
import type { BatchLogEntry, SettlementDetail } from '../types';

const LIVE_STATUSES = new Set([
  'CREATED',
  'FILES_RECEIVED',
  'VALIDATED',
  'NORMALIZED',
  'RECONCILIATION_RUNNING',
  'RECONCILIATION_COMPLETED',
  'EXCEPTIONS_IDENTIFIED',
  'EXCEPTIONS_RESOLVED',
  'TAX_PROCESSING',
  'SETTLEMENT_PROCESSING',
  'REPORTING',
]);

function LogView({
  entries,
  filter,
  timeZone,
}: {
  entries: BatchLogEntry[];
  filter: string;
  timeZone: string;
}) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const shown = entries.filter((e) => filter === 'ALL' || e.level === filter);

  const toggle = (seq: number) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(seq)) next.delete(seq);
      else next.add(seq);
      return next;
    });

  if (shown.length === 0) {
    return <div className="grid-empty">No log entries{filter === 'ALL' ? ' yet' : ` at level ${filter}`}.</div>;
  }

  return (
    <div className="log">
      {shown.map((entry) => {
        const hasDetail = entry.detail_json && Object.keys(entry.detail_json).length > 0;
        const isOpen = expanded.has(entry.seq);
        return (
          <div key={entry.seq}>
            <div className={`log__row log__row--${entry.level}`}>
              <span className="log__seq">{entry.seq}</span>
              <span className="log__time">{formatTime(entry.created_at, timeZone)}</span>
              <span className="log__stage">{entry.stage}</span>
              <span className="log__msg">{entry.message}</span>
              {hasDetail && (
                <button type="button" className="log__expander" onClick={() => toggle(entry.seq)}>
                  {isOpen ? '[hide]' : '[detail]'}
                </button>
              )}
            </div>
            {hasDetail && isOpen && (
              <div className="log__detail">{JSON.stringify(entry.detail_json, null, 2)}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

const REASON_LABEL: Record<string, string> = {
  NO_RULES_CONFIGURED: 'No fee/tax treatment is configured for this client',
  NET_EXCEEDS_GROSS: 'The observed amount is larger than the gross',
  RULES_PRODUCE_A_DIFFERENT_NET: 'The configured rules were applied but arrive at a different net',
  EXPLAINED_BY_CONFIGURED_RULES: 'Explained by the configured rules',
};

/**
 * One settlement, shown as arithmetic rather than as a row of numbers.
 *
 * When the configured rules do NOT explain a gap, this shows what they were
 * asked and what they answered. "No configured rule accounts for it" on its
 * own cannot distinguish a missing configuration from a wrong rate from a
 * difference that was never a charge -- and those need different responses.
 */
function SettlementCard({ settlement }: { settlement: SettlementDetail }) {
  const evaluation = settlement.fee_rule_evaluation;
  const attempted = evaluation?.attempted_lines ?? [];

  return (
    <div className="pane" style={{ marginBottom: 9 }}>
      <div className="toolbar">
        <span className="strong">Gross {formatMoney(settlement.gross_amount)}</span>
        <span className="muted">→ observed {formatMoney(settlement.net_amount_observed)}</span>
        <Badge value={settlement.is_fully_explained ? 'OK' : 'WARN'} />
        {settlement.match_type && (
          <span className="small muted">matched by {settlement.match_type.replace(/_/g, ' ').toLowerCase()}</span>
        )}
      </div>

      <div className="pane__body">
        {settlement.is_fully_explained ? (
          <div className="calc">
            <div className="calc__row">
              <span className="calc__label">Gross</span>
              <span className="calc__value">{formatMoney(settlement.gross_amount)}</span>
            </div>
            {settlement.components.map((component, index) => (
              <div className="calc__row" key={index}>
                <span className="calc__label">
                  − {component.description ?? component.type.replace(/_/g, ' ')}
                </span>
                <span className="calc__value">{formatMoney(component.amount)}</span>
              </div>
            ))}
            <div className="calc__row calc__row--total">
              <span className="calc__label">Net (expected and observed agree)</span>
              <span className="calc__value">{formatMoney(settlement.net_amount_observed)}</span>
            </div>
          </div>
        ) : (
          <>
            <div className="callout callout--warn">
              <strong>{evaluation ? REASON_LABEL[evaluation.reason] ?? evaluation.reason : 'Unexplained variance'}</strong>
              <br />
              {evaluation?.narrative ??
                'No configured fee or tax rule accounts for the difference.'}
            </div>

            {attempted.length > 0 && (
              <>
                <div className="small strong" style={{ marginBottom: 4 }}>
                  What the configured rules would have deducted
                  {evaluation?.applicable_when && (
                    <span className="muted">
                      {'  '}(applies to {evaluation.applicable_when.internal_instrument_type} ↔{' '}
                      {evaluation.applicable_when.external_instrument_type})
                    </span>
                  )}
                </div>
                <div className="calc">
                  <div className="calc__row">
                    <span className="calc__label">Gross</span>
                    <span className="calc__value">{formatMoney(settlement.gross_amount)}</span>
                  </div>
                  {attempted.map((line, index) => (
                    <div className="calc__row" key={index}>
                      <span className="calc__label">
                        − {line.label}
                        {line.verification_status && (
                          <span className="muted"> [{line.verification_status}]</span>
                        )}
                        {line.source_reference && (
                          <span className="muted"> · {line.source_reference}</span>
                        )}
                      </span>
                      <span className="calc__value">{formatMoney(line.amount)}</span>
                    </div>
                  ))}
                  <div className="calc__row">
                    <span className="calc__label">Net the rules arrive at</span>
                    <span className="calc__value">{formatMoney(evaluation?.net_if_rules_applied)}</span>
                  </div>
                  <div className="calc__row">
                    <span className="calc__label">Net the feed actually reported</span>
                    <span className="calc__value">{formatMoney(settlement.net_amount_observed)}</span>
                  </div>
                  <div className="calc__row calc__row--total">
                    <span className="calc__label">
                      Still unexplained (tolerance {evaluation?.rounding_tolerance ?? '—'})
                    </span>
                    <span className="calc__value">{formatMoney(evaluation?.residual)}</span>
                  </div>
                </div>
              </>
            )}

            {attempted.length === 0 && (
              <div className="calc">
                <div className="calc__row">
                  <span className="calc__label">Gross</span>
                  <span className="calc__value">{formatMoney(settlement.gross_amount)}</span>
                </div>
                <div className="calc__row">
                  <span className="calc__label">Observed</span>
                  <span className="calc__value">{formatMoney(settlement.net_amount_observed)}</span>
                </div>
                <div className="calc__row calc__row--total">
                  <span className="calc__label">Difference</span>
                  <span className="calc__value">{formatMoney(evaluation?.difference)}</span>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export function BatchRunBlotter({ blotter }: { blotter: Blotter }) {
  const { revision, refresh, clientById } = useWorkspace();
  const [logFilter, setLogFilter] = useState('ALL');
  const batchId = blotter.batchId!;
  const client = clientById(blotter.clientId);

  const report = useLoader(() => api.batchReport(batchId), [batchId, revision]);
  const data = report.data;
  const live = data ? LIVE_STATUSES.has(data.batch.status) : false;

  useLoader(
    async () => {
      if (live) report.reload();
      return null;
    },
    [live],
    { pollMs: live ? 1200 : undefined },
  );

  if (report.error) {
    return (
      <div className="blotter">
        <header className="blotter__header">
          <span className="blotter__title">Batch run</span>
        </header>
        <div className="blotter__body">
          <div className="callout callout--error">{report.error}</div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="blotter">
        <div className="blotter__body">
          <span className="spinner" /> Loading batch…
        </div>
      </div>
    );
  }

  const { batch, reconciliation, exceptions, settlements, cash, files, transactions, log } = data;
  const timeZone = client?.display_timezone ?? DEFAULT_DISPLAY_TIMEZONE;

  return (
    <div className="blotter">
      <header className="blotter__header">
        <Icon name="log" size={16} />
        <span className="blotter__title">{batch.batch_code}</span>
        <span className="blotter__subtitle">
          {batch.batch_definition_name ?? '—'} · {client?.code ?? ''} · business date{' '}
          {batch.business_date ?? '—'}
        </span>
        <span className="blotter__spacer" />
        <Badge value={batch.status} />
        {live && (
          <span style={{ width: 110 }}>
            <Progress pct={batch.progress_pct} />
          </span>
        )}
      </header>

      <div className="toolbar">
        <span className="small">
          Triggered by <strong>{batch.triggered_by}</strong> ({batch.triggered_by_type}) at{' '}
          {formatTime(batch.created_at, timeZone)}
          {batch.closed_at ? ` · closed ${formatTime(batch.closed_at, timeZone)}` : ''}
        </span>
        <span className="toolbar__spacer" />
        {live && (
          <span className="small">
            <span className="spinner" /> {batch.current_stage}
          </span>
        )}
        <button type="button" className="btn" onClick={refresh}>
          <Icon name="refresh" size={12} /> Refresh
        </button>
      </div>

      <div className="blotter__body">
        {batch.failure_reason && (
          <div className="callout callout--error">
            <strong>Run failed at {batch.current_stage}.</strong>
            <br />
            {batch.failure_reason}
          </div>
        )}

        <div className="kpis">
          <Kpi label="Transactions" value={transactions.total} note={`${files.length} file(s) imported`} />
          <Kpi
            label="Matched"
            value={reconciliation.match_rate_pct === null ? '—' : `${reconciliation.match_rate_pct}%`}
            note={`${reconciliation.match_count} match groups`}
          />
          <Kpi
            label="Exceptions"
            value={exceptions.total}
            note={`${exceptions.open} open`}
          />
          <Kpi
            label="At risk"
            value={formatMoney(exceptions.total_amount_at_risk)}
            note="open exceptions"
          />
          <Kpi
            label="Settlements"
            value={settlements.total}
            note={`${settlements.unexplained} unexplained`}
          />
          <Kpi
            label="Confirmed cash"
            value={formatMoney(cash.confirmed_cash)}
            note={cash.as_of ? `as of ${cash.as_of}` : undefined}
          />
        </div>

        <Pane
          title="Run log"
          hint={`${log?.length ?? 0} entries — exceptions are written here in full`}
          flush
          actions={
            <select value={logFilter} onChange={(e) => setLogFilter(e.target.value)}>
              <option value="ALL">All levels</option>
              <option value="INFO">Info</option>
              <option value="WARN">Warnings</option>
              <option value="ERROR">Errors</option>
              <option value="EXCEPTION">Exceptions</option>
            </select>
          }
        >
          <LogView entries={log ?? []} filter={logFilter} timeZone={timeZone} />
        </Pane>

        <Pane title="Match breakdown" hint={`${reconciliation.match_count} groups`}>
          <Grid
            columns={[
              { key: 'type', label: 'Match type' },
              { key: 'count', label: 'Groups', numeric: true },
            ]}
            empty="No matches were made in this run."
          >
            {Object.entries(reconciliation.matches_by_type).map(([type, count]) => (
              <tr key={type}>
                <td>{type.replace(/_/g, ' ')}</td>
                <td className="num">{count}</td>
              </tr>
            ))}
          </Grid>
          {Object.keys(reconciliation.matches_by_cardinality).length > 0 && (
            <div className="small muted" style={{ marginTop: 6 }}>
              Cardinality:{' '}
              {Object.entries(reconciliation.matches_by_cardinality)
                .map(([k, v]) => `${k.replace(/_/g, ':').toLowerCase()} ${v}`)
                .join(' · ')}
            </div>
          )}
        </Pane>

        <Pane
          title="Exceptions"
          hint={`${exceptions.open} open · ${formatMoney(exceptions.total_amount_at_risk)} at risk`}
          flush
        >
          <Grid
            columns={[
              { key: 'type', label: 'Type' },
              { key: 'sev', label: 'Severity' },
              { key: 'amount', label: 'Amount impact', numeric: true },
              { key: 'cause', label: 'Likely cause (system)' },
              { key: 'action', label: 'Recommended action' },
              { key: 'txns', label: 'Transactions' },
            ]}
            empty="No exceptions: every transaction was resolved."
          >
            {exceptions.items.map((item) => (
              <tr key={item.id}>
                <td className="nowrap">{item.exception_type.replace(/_/g, ' ')}</td>
                <td>
                  <Badge value={item.severity} />
                </td>
                <td className="num">{formatMoney(item.amount_impact)}</td>
                <td>{item.likely_cause ?? '—'}</td>
                <td>{item.recommended_action ?? '—'}</td>
                <td className="small">
                  {item.transactions.map((txn) => (
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

        <Pane
          title="Settlement decomposition"
          hint={`${settlements.total} settlement(s), ${settlements.unexplained} not fully explained`}
          defaultOpen={settlements.unexplained > 0}
        >
          {settlements.components.length === 0 ? (
            <div className="grid-empty">No settlement decomposition was required in this run.</div>
          ) : (
            settlements.components.map((settlement) => (
              <SettlementCard key={settlement.id} settlement={settlement} />
            ))
          )}
        </Pane>

        <Pane title="Imported files" defaultOpen={false} flush>
          <Grid
            columns={[
              { key: 'file', label: 'File' },
              { key: 'format', label: 'Format' },
              { key: 'bytes', label: 'Bytes', numeric: true },
              { key: 'sha', label: 'SHA-256' },
            ]}
            empty="No files were imported."
          >
            {files.map((file) => (
              <tr key={file.checksum_sha256}>
                <td className="mono">{file.filename}</td>
                <td>{file.file_format}</td>
                <td className="num">{file.size_bytes.toLocaleString()}</td>
                <td className="mono small">{file.checksum_sha256.slice(0, 24)}…</td>
              </tr>
            ))}
          </Grid>
        </Pane>
      </div>
    </div>
  );
}
