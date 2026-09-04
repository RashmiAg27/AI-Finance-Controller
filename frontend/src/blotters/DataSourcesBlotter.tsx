import { useState } from 'react';
import { api } from '../api/client';
import { Icon } from '../components/Icon';
import { Badge, Grid, Kpi, Pane } from '../components/Office';
import { useLoader, useWorkspace, type Blotter } from '../app/WorkspaceContext';
import { formatDateTime } from '../lib/format';
import type { ImportSource } from '../types';
import { ImportSourceEditor } from './ImportSourceEditor';

const KIND_ICON: Record<string, 'folder' | 'mail' | 'server' | 'cloud'> = {
  LOCAL_DIRECTORY: 'folder',
  EMAIL_INBOX: 'mail',
  SFTP_CONNECTION: 'server',
  API_CONNECTION: 'cloud',
};

/**
 * Everything a client's data arrives from, in one window: the bank accounts
 * that movements belong to, the connections files come over, and the feed
 * schemas the engine maps into canonical form.
 *
 * The accounts pane is first on purpose. It is the answer to "reconcile
 * against what?" -- a client is not a reconciliation unit, an account is.
 */
export function DataSourcesBlotter({ blotter }: { blotter: Blotter }) {
  const { revision, refresh, clientById } = useWorkspace();
  const clientId = blotter.clientId;
  const client = clientById(clientId);
  const [editing, setEditing] = useState<ImportSource | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const accounts = useLoader(() => api.bankAccounts(clientId), [clientId, revision]);
  const sources = useLoader(() => api.importSources(clientId), [clientId, revision]);
  const feeds = useLoader(() => api.dataSources(clientId), [clientId, revision]);
  const definitions = useLoader(() => api.batchDefinitions(clientId), [clientId, revision]);

  const accountRows = accounts.data ?? [];
  const definitionRows = definitions.data ?? [];

  const cyclesFor = (accountId: string) =>
    definitionRows.filter((d) => d.bank_account_id === accountId);

  return (
    <div className="blotter">
      <header className="blotter__header">
        <Icon name="connect" size={18} />
        <span className="blotter__title">Data Sources &amp; Accounts</span>
        <span className="blotter__subtitle">{client ? `${client.name} (${client.code})` : clientId}</span>
        <span className="blotter__spacer" />
        <span className="small muted">
          {accountRows.length} accounts · {(sources.data ?? []).length} connections ·{' '}
          {(feeds.data ?? []).length} feeds
        </span>
      </header>

      <div className="toolbar">
        <button
          type="button"
          className="btn"
          disabled={!sources.data?.length}
          onClick={() => sources.data && setEditing(sources.data[0])}
        >
          <Icon name="edit" size={14} /> Edit first connection
        </button>
        <span className="toolbar__spacer" />
        <button type="button" className="btn" onClick={refresh}>
          <Icon name="refresh" size={14} /> Refresh
        </button>
      </div>

      <div className="blotter__body">
        {notice && <div className="callout">{notice}</div>}
        {accounts.error && <div className="callout callout--error">{accounts.error}</div>}

        <div className="kpis">
          <Kpi label="Bank accounts" value={accountRows.length} note="reconciliation units" />
          <Kpi label="Connections" value={(sources.data ?? []).length} note="where files arrive" />
          <Kpi label="Feed schemas" value={(feeds.data ?? []).length} note="mapped to canonical" />
          <Kpi label="Configured cycles" value={definitionRows.length} />
        </div>

        <Pane
          title="Bank accounts"
          hint="A client is the parent entity; each account is reconciled separately"
          flush
        >
          <Grid
            columns={[
              { key: 'account', label: 'Account' },
              { key: 'bank', label: 'Bank' },
              { key: 'number', label: 'Number' },
              { key: 'ifsc', label: 'IFSC' },
              { key: 'purpose', label: 'Purpose' },
              { key: 'gl', label: 'GL code' },
              { key: 'cycles', label: 'Reconciled by' },
            ]}
            empty={accounts.loading ? 'Loading accounts…' : 'No bank accounts configured.'}
          >
            {accountRows.map((account) => {
              const cycles = cyclesFor(account.id);
              return (
                <tr key={account.id}>
                  <td>
                    <div className="strong mono">{account.account_code}</div>
                    <div className="muted small">{account.display_name}</div>
                  </td>
                  <td className="nowrap">{account.bank_name}</td>
                  <td className="mono nowrap">{account.account_number_masked}</td>
                  <td className="mono small">{account.ifsc ?? '—'}</td>
                  <td>
                    <Badge value={account.purpose} />
                  </td>
                  <td className="mono small">{account.gl_code ?? '—'}</td>
                  <td className="small">
                    {cycles.length === 0 ? (
                      <span className="muted">no cycle configured</span>
                    ) : (
                      cycles.map((c) => (
                        <div key={c.id}>
                          <span className="mono">{c.code}</span>{' '}
                          <span className="muted">{c.reconciliation_label}</span>
                        </div>
                      ))
                    )}
                  </td>
                </tr>
              );
            })}
          </Grid>
        </Pane>

        <Pane title="Connections" hint="How files physically arrive" flush>
          <Grid
            columns={[
              { key: 'code', label: 'Connection' },
              { key: 'kind', label: 'Kind' },
              { key: 'where', label: 'Location' },
              { key: 'poll', label: 'Last poll' },
              { key: 'edit', label: '', width: 70 },
            ]}
            empty={sources.loading ? 'Loading connections…' : 'No import sources configured.'}
          >
            {(sources.data ?? []).map((source) => (
              <tr key={source.id}>
                <td>
                  <div className="strong mono">{source.code}</div>
                  <div className="muted small">{source.name}</div>
                </td>
                <td className="nowrap">
                  <Icon name={KIND_ICON[source.kind] ?? 'connect'} size={14} />{' '}
                  {source.kind.replace(/_/g, ' ').toLowerCase()}
                </td>
                <td className="mono small" style={{ wordBreak: 'break-all' }}>
                  {source.location}
                </td>
                <td className="small">
                  {source.last_status ? (
                    <>
                      <Badge value={source.last_status} />
                      <div className="muted">
                        {formatDateTime(source.last_polled_at, client?.display_timezone)}
                      </div>
                      <div className="muted">{source.last_message}</div>
                    </>
                  ) : (
                    <span className="muted">not polled since last edit</span>
                  )}
                </td>
                <td>
                  <button type="button" className="btn" onClick={() => setEditing(source)}>
                    Edit
                  </button>
                </td>
              </tr>
            ))}
          </Grid>
        </Pane>

        <Pane
          title="Feed schemas"
          hint="Each arrives with its own column names; the canonical mapping absorbs that"
          flush
          defaultOpen={false}
        >
          <Grid
            columns={[
              { key: 'source', label: 'Feed' },
              { key: 'role', label: 'Role' },
              { key: 'format', label: 'Format' },
              { key: 'used', label: 'Used by' },
            ]}
            empty="No data sources configured."
          >
            {(feeds.data ?? []).map((feed) => (
              <tr key={feed.source_id}>
                <td className="mono">{feed.source_id}</td>
                <td>
                  <Badge value={feed.role} />
                </td>
                <td>{feed.file_format}</td>
                <td className="small">
                  {definitionRows
                    .filter((d) => d.source_ids.includes(feed.source_id))
                    .map((d) => d.code)
                    .join(', ') || <span className="muted">not used by any cycle</span>}
                </td>
              </tr>
            ))}
          </Grid>
        </Pane>

        <div className="callout">
          Open <strong>Matching Rules</strong> to see how each feed's own columns map onto the
          canonical fields the engine actually reconciles on.
        </div>
      </div>

      {editing && (
        <ImportSourceEditor
          source={editing}
          onClose={() => setEditing(null)}
          onSaved={(updated) => {
            setEditing(updated);
            setNotice(`Connection ${updated.code} saved.`);
            refresh();
          }}
        />
      )}
    </div>
  );
}
