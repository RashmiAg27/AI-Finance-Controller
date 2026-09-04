import { useMemo, useState } from 'react';
import { api } from '../api/client';
import { Icon } from '../components/Icon';
import { Badge, Dialog, Field, Grid, Progress, SelectField } from '../components/Office';
import { useLoader, useRibbonCommands, useWorkspace, type Blotter } from '../app/WorkspaceContext';
import type { BatchDefinition, DataSource, ImportSource, ReconciliationType } from '../types';

/** The one-line reminder of which differences are legitimate for a
 *  reconciliation type -- shown on the group header so an operator reading a
 *  gross/net gap knows immediately whether it is a break or the point. */
function recTypeHint(code: string, catalogue: ReconciliationType[] | null): string {
  const entry = catalogue?.find((t) => t.code === code);
  return entry?.legitimate_differences ? `  ·  Expected here: ${entry.legitimate_differences}` : '';
}
import { ImportSourceEditor } from './ImportSourceEditor';

const BATCH_TYPES = [
  'DAILY_STATEMENT',
  'SETTLEMENT_OBLIGATION',
  'POSITION_HOLDING',
  'COLLECTION_MANDATE',
  'FEE_INVOICE',
  'INTRADAY_SWEEP',
];
const TRIGGER_TYPES = ['SCHEDULED', 'FILE_ARRIVAL', 'MANUAL', 'UPSTREAM_EVENT'];

/* --------------------------------------------------------------------------
   Batch definition editor
   -------------------------------------------------------------------------- */

function BatchDefinitionEditor({
  definition,
  importSources,
  dataSources,
  onClose,
  onSaved,
}: {
  definition: BatchDefinition;
  importSources: ImportSource[];
  dataSources: DataSource[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState({
    name: definition.name,
    description: definition.description ?? '',
    batch_type: definition.batch_type,
    trigger_type: definition.trigger_type,
    trigger_detail: definition.trigger_detail ?? '',
    import_source_id: definition.import_source_id ?? '',
    source_ids: [...definition.source_ids],
    enabled: definition.enabled,
    cutoff_time: definition.cutoff_time ?? '',
    sla_minutes: definition.sla_minutes,
    owner_team: definition.owner_team ?? '',
  });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const toggleSource = (sourceId: string) =>
    setDraft((d) => ({
      ...d,
      source_ids: d.source_ids.includes(sourceId)
        ? d.source_ids.filter((s) => s !== sourceId)
        : [...d.source_ids, sourceId],
    }));

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.updateBatchDefinition(definition.id, {
        ...draft,
        import_source_id: draft.import_source_id || null,
        description: draft.description || null,
        trigger_detail: draft.trigger_detail || null,
        cutoff_time: draft.cutoff_time || null,
        owner_team: draft.owner_team || null,
      });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      title={`Batch settings — ${definition.code}`}
      onClose={onClose}
      width={640}
      footer={
        <>
          <button type="button" className="btn btn--primary" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
        </>
      }
    >
      {error && <div className="dialog__error">{error}</div>}

      <Field label="Name">
        <input type="text" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
      </Field>
      <Field label="Description">
        <textarea
          rows={2}
          style={{ width: '100%' }}
          value={draft.description}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
        />
      </Field>
      <Field label="Batch type">
        <SelectField
          value={draft.batch_type}
          options={BATCH_TYPES.map((t) => ({ value: t, label: t.replace(/_/g, ' ') }))}
          onChange={(v) => setDraft({ ...draft, batch_type: v })}
        />
      </Field>
      <Field label="Trigger">
        <SelectField
          value={draft.trigger_type}
          options={TRIGGER_TYPES.map((t) => ({ value: t, label: t.replace(/_/g, ' ') }))}
          onChange={(v) => setDraft({ ...draft, trigger_type: v })}
        />
      </Field>
      <Field
        label="Trigger detail"
        note="Free text describing when this fires — a schedule, an event name, a desk instruction."
      >
        <input
          type="text"
          value={draft.trigger_detail}
          onChange={(e) => setDraft({ ...draft, trigger_detail: e.target.value })}
        />
      </Field>

      <Field
        label="Import source"
        note="Where this batch's files are fetched from when it runs."
      >
        <SelectField
          value={draft.import_source_id}
          options={[
            { value: '', label: '— none —' },
            ...importSources.map((s) => ({ value: s.id, label: `${s.code} · ${s.kind.replace(/_/g, ' ')}` })),
          ]}
          onChange={(v) => setDraft({ ...draft, import_source_id: v })}
        />
      </Field>

      <Field label="Data sources" note="What this cycle must receive before it can be processed.">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
          {dataSources.map((source) => (
            <label key={source.source_id} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={draft.source_ids.includes(source.source_id)}
                onChange={() => toggleSource(source.source_id)}
              />
              <span className="mono">{source.source_id}</span>
              <span className="muted small">({source.role.toLowerCase()}, {source.file_format})</span>
            </label>
          ))}
        </div>
      </Field>

      <Field label="Cut-off">
        <input
          type="text"
          value={draft.cutoff_time}
          placeholder="19:30 IST"
          onChange={(e) => setDraft({ ...draft, cutoff_time: e.target.value })}
        />
      </Field>
      <Field label="SLA (minutes)">
        <input
          type="number"
          value={draft.sla_minutes}
          onChange={(e) => setDraft({ ...draft, sla_minutes: Number(e.target.value) })}
        />
      </Field>
      <Field label="Owner team">
        <input
          type="text"
          value={draft.owner_team}
          onChange={(e) => setDraft({ ...draft, owner_team: e.target.value })}
        />
      </Field>
      <Field label="Enabled">
        <input
          type="checkbox"
          checked={draft.enabled}
          onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
        />
      </Field>

      <div className="callout">
        Saving takes effect on the next run. A batch already in flight keeps the configuration version
        it started with.
      </div>
    </Dialog>
  );
}

/* --------------------------------------------------------------------------
   The window
   -------------------------------------------------------------------------- */

export function ReconciliationBlotter({ blotter }: { blotter: Blotter }) {
  const { revision, refresh, openBlotter, clientById, setStatus, setBusy } = useWorkspace();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editingDefinition, setEditingDefinition] = useState<BatchDefinition | null>(null);
  const [editingSource, setEditingSource] = useState<ImportSource | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const clientId = blotter.clientId;
  const client = clientById(clientId);

  const definitions = useLoader(() => api.batchDefinitions(clientId), [clientId, revision]);
  const reconTypes = useLoader(() => api.reconciliationTypes(), []);
  const importSources = useLoader(() => api.importSources(clientId), [clientId, revision]);
  const dataSources = useLoader(() => api.dataSources(clientId), [clientId, revision]);

  const rows = definitions.data ?? [];
  const anyRunning = rows.some((d) => d.state === 'RUNNING');

  // Poll only while something is actually moving. An idle blotter must not
  // hammer the API just because it happens to be open.
  useLoader(
    async () => {
      if (anyRunning) definitions.reload();
      return null;
    },
    [anyRunning],
    { pollMs: anyRunning ? 1500 : undefined },
  );

  // Grouped by WHAT is being proved. Two Bank<->GL cycles for one client are
  // not duplicates -- they are two different accounts, and showing them under
  // one heading is what makes that legible rather than confusing.
  const grouped = useMemo(() => {
    const buckets = new Map<string, BatchDefinition[]>();
    for (const row of rows) {
      const list = buckets.get(row.reconciliation_type) ?? [];
      list.push(row);
      buckets.set(row.reconciliation_type, list);
    }
    return [...buckets.entries()];
  }, [rows]);

  const selected = useMemo(() => rows.find((d) => d.id === selectedId) ?? null, [rows, selectedId]);
  const selectedImportSource = useMemo(
    () => (importSources.data ?? []).find((s) => s.id === selected?.import_source_id) ?? null,
    [importSources.data, selected],
  );

  const openRun = (definition: BatchDefinition) => {
    if (!definition.latest_run) return;
    openBlotter({
      kind: 'batch',
      clientId,
      batchId: definition.latest_run.id,
      title: `Batch run — ${definition.latest_run.batch_code}`,
      subtitle: definition.latest_run.batch_code,
    });
  };

  const run = async (definitionIds?: string[]) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = definitionIds?.length === 1
        ? await api.runBatchDefinition(definitionIds[0])
        : await api.runBatchDefinitions(clientId, definitionIds);

      const queued = result.queued.map((q) => q.batch_code);
      const skipped = result.skipped.map((s) => `${s.code} (${s.reason})`);
      const message = [
        queued.length ? `Queued: ${queued.join(', ')}` : 'Nothing queued.',
        skipped.length ? `Skipped: ${skipped.join('; ')}` : '',
      ]
        .filter(Boolean)
        .join('  ·  ');
      setNotice(message);
      setStatus(message);

      if (result.queued.length === 1) {
        const only = result.queued[0];
        openBlotter({
          kind: 'batch',
          clientId,
          batchId: only.id,
          title: `Batch run — ${only.batch_code}`,
          subtitle: only.batch_code,
        });
      }
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  useRibbonCommands(blotter.id, [
    { id: 'run', group: 'Run', label: 'Run selected', primary: true,
      disabled: !selected || !selected.enabled,
      title: selected ? `Run ${selected.code}` : 'Select a cycle first',
      run: () => selected && run([selected.id]) },
    { id: 'run-all', group: 'Run', label: 'Run all cycles', run: () => run() },
    { id: 'edit-batch', group: 'Configure', label: 'Edit batch settings',
      disabled: !selected, run: () => selected && setEditingDefinition(selected) },
    { id: 'edit-source', group: 'Configure', label: 'Edit import source',
      disabled: !selectedImportSource,
      run: () => selectedImportSource && setEditingSource(selectedImportSource) },
    { id: 'open-run', group: 'Inspect', label: 'Open last run',
      disabled: !selected?.latest_run, run: () => selected && openRun(selected) },
  ]);

  return (
    <div className="blotter">
      <header className="blotter__header">
        <Icon name="recon" size={18} />
        <span className="blotter__title">Reconciliation Management</span>
        <span className="blotter__subtitle">
          {client ? `${client.name} (${client.code})` : clientId}
        </span>
        <span className="blotter__spacer" />
        <span className="small muted">{rows.length} configured batch{rows.length === 1 ? '' : 'es'}</span>
      </header>

      <div className="toolbar">
        <button
          type="button"
          className="btn btn--primary"
          disabled={!selected || !selected.enabled}
          onClick={() => selected && run([selected.id])}
        >
          <Icon name="run" size={12} /> Run
        </button>
        <button type="button" className="btn" onClick={() => run()}>
          <Icon name="runAll" size={12} /> Run all
        </button>
        <span style={{ width: 8 }} />
        <button
          type="button"
          className="btn"
          disabled={!selected}
          onClick={() => selected && setEditingDefinition(selected)}
        >
          <Icon name="edit" size={12} /> Edit batch
        </button>
        <button
          type="button"
          className="btn"
          disabled={!selectedImportSource}
          onClick={() => selectedImportSource && setEditingSource(selectedImportSource)}
        >
          <Icon name="connect" size={12} /> Edit import source
        </button>
        <button
          type="button"
          className="btn"
          disabled={!selected?.latest_run}
          onClick={() => selected && openRun(selected)}
        >
          <Icon name="log" size={12} /> Open last run
        </button>
        <span className="toolbar__spacer" />
        <button type="button" className="btn" onClick={refresh}>
          <Icon name="refresh" size={12} /> Refresh
        </button>
      </div>

      <div className="blotter__body">
        {definitions.error && <div className="callout callout--error">{definitions.error}</div>}
        {error && <div className="callout callout--error">{error}</div>}
        {notice && <div className="callout">{notice}</div>}

        <Grid
          columns={[
            { key: 'code', label: 'Batch' },
            { key: 'account', label: 'Account' },
            { key: 'state', label: 'State' },
            { key: 'trigger', label: 'Trigger' },
            { key: 'import', label: 'Import source' },
            { key: 'sources', label: 'Data sources' },
            { key: 'data', label: 'Data' },
            { key: 'run', label: 'Last run' },
          ]}
          empty={definitions.loading ? 'Loading configured batches…' : 'No batches configured for this client.'}
        >
          {grouped.flatMap(([reconType, groupRows]) => [
            <tr className="grid__group" key={`group-${reconType}`}>
              <td colSpan={8}>
                {groupRows[0].reconciliation_label ?? reconType}
                <span className="muted small" style={{ fontWeight: 400 }}>
                  {'  '}· {groupRows.length} cycle{groupRows.length === 1 ? '' : 's'}
                  {recTypeHint(reconType, reconTypes.data)}
                </span>
              </td>
            </tr>,
            ...groupRows.map((definition) => (
            <tr
              key={definition.id}
              className={`is-clickable${selectedId === definition.id ? ' is-selected' : ''}`}
              onClick={() => setSelectedId(definition.id)}
              onDoubleClick={() => openRun(definition)}
            >
              <td>
                <div className="strong mono">{definition.code}</div>
                <div className="muted">{definition.name}</div>
              </td>
              <td className="nowrap small">
                {definition.bank_account_label ?? (
                  <span className="muted">spans accounts</span>
                )}
              </td>
              <td>
                <Badge value={definition.state} />
                {definition.state === 'RUNNING' && definition.latest_run && (
                  <div style={{ marginTop: 3 }}>
                    <Progress pct={definition.latest_run.progress_pct} />
                    <div className="muted small">{definition.latest_run.current_stage}</div>
                  </div>
                )}
              </td>
              <td className="nowrap">
                <div>{definition.trigger_type.replace(/_/g, ' ').toLowerCase()}</div>
                <div className="muted small">{definition.trigger_detail ?? '—'}</div>
              </td>
              <td>
                <div>{definition.import_source_code ?? <span className="muted">— none —</span>}</div>
                <div className="muted small mono" style={{ wordBreak: 'break-all' }}>
                  {definition.import_location ?? ''}
                </div>
              </td>
              <td className="mono small">{definition.source_ids.join(', ')}</td>
              <td>
                {definition.data_available === null ? (
                  <span className="muted">—</span>
                ) : definition.data_available ? (
                  <Badge value="OK" />
                ) : (
                  <>
                    <Badge value="AWAITING_DATA" />
                    <div className="muted small">missing {definition.missing_source_ids.join(', ')}</div>
                  </>
                )}
              </td>
              <td>
                {definition.latest_run ? (
                  <>
                    <div className="mono small">{definition.latest_run.batch_code}</div>
                    <Badge value={definition.latest_run.status} />
                    {definition.latest_run.failure_reason && (
                      <div className="small" style={{ color: 'var(--error)' }}>
                        {definition.latest_run.failure_reason}
                      </div>
                    )}
                  </>
                ) : (
                  <span className="muted">never run</span>
                )}
              </td>
            </tr>
            )),
          ])}
        </Grid>

        {selected && (
          <div className="callout" style={{ marginTop: 9 }}>
            <strong>{selected.name}</strong> — {selected.description ?? 'No description.'}
            <br />
            Proves: <strong>{selected.reconciliation_label ?? selected.reconciliation_type}</strong>
            {' · '}Account: <strong>{selected.bank_account_label ?? 'spans accounts'}</strong>
            <br />
            Owner: {selected.owner_team ?? '—'} · Cut-off: {selected.cutoff_time ?? '—'} · SLA:{' '}
            {selected.sla_minutes} min · Last edited by {selected.updated_by ?? 'system'}
          </div>
        )}
      </div>

      {editingDefinition && (
        <BatchDefinitionEditor
          definition={editingDefinition}
          importSources={importSources.data ?? []}
          dataSources={dataSources.data ?? []}
          onClose={() => setEditingDefinition(null)}
          onSaved={() => {
            setEditingDefinition(null);
            setNotice('Batch settings saved. They apply from the next run.');
            refresh();
          }}
        />
      )}

      {editingSource && (
        <ImportSourceEditor
          source={editingSource}
          onClose={() => setEditingSource(null)}
          onSaved={(updated) => {
            setEditingSource(updated);
            setNotice(`Import source ${updated.code} saved.`);
            refresh();
          }}
        />
      )}
    </div>
  );
}
