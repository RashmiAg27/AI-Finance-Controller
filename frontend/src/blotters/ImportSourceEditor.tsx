import { useState } from 'react';
import { api } from '../api/client';
import { Badge, Dialog, Field, SelectField } from '../components/Office';
import type { ImportProbeResult, ImportSource, ImportSourceKind } from '../types';

/**
 * Which connection fields each kind accepts. This mirrors
 * app.domains.ingestion.import_sources._CONNECTION_FIELDS -- the server
 * validates independently and rejects anything else, so a mismatch here shows
 * up as a clear error rather than a silently dropped setting.
 */
type FieldType = 'text' | 'number' | 'bool' | 'list';

interface FieldSpec {
  name: string;
  label: string;
  type: FieldType;
  required?: boolean;
  placeholder?: string;
  help?: string;
}

const CONNECTION_FIELDS: Record<ImportSourceKind, FieldSpec[]> = {
  LOCAL_DIRECTORY: [
    {
      name: 'directory',
      label: 'Directory',
      type: 'text',
      required: true,
      placeholder: 'D:\\feeds\\meridian\\bank  or  data/inbound/mrdn/bank',
      help: 'Read from this machine. Absolute, or relative to the project root.',
    },
    { name: 'file_pattern', label: 'File pattern', type: 'text', placeholder: '*.*' },
    { name: 'archive_after_import', label: 'Archive after import', type: 'bool' },
  ],
  EMAIL_INBOX: [
    { name: 'host', label: 'IMAP host', type: 'text', required: true },
    { name: 'port', label: 'Port', type: 'number' },
    { name: 'username', label: 'Mailbox user', type: 'text', required: true },
    { name: 'mailbox', label: 'Folder', type: 'text', required: true, placeholder: 'INBOX/Recon' },
    {
      name: 'sender_allowlist',
      label: 'Accepted senders',
      type: 'list',
      help: 'Comma separated. Empty means any sender.',
    },
    { name: 'subject_pattern', label: 'Subject pattern', type: 'text' },
    { name: 'attachment_pattern', label: 'Attachment pattern', type: 'text', placeholder: '*.csv' },
  ],
  SFTP_CONNECTION: [
    { name: 'host', label: 'Host', type: 'text', required: true },
    { name: 'port', label: 'Port', type: 'number' },
    { name: 'username', label: 'Username', type: 'text', required: true },
    { name: 'remote_path', label: 'Remote path', type: 'text', required: true },
    { name: 'key_reference', label: 'Key reference', type: 'text', placeholder: 'vault://...' },
    { name: 'file_pattern', label: 'File pattern', type: 'text' },
  ],
  API_CONNECTION: [
    { name: 'base_url', label: 'Base URL', type: 'text', required: true },
    { name: 'endpoint', label: 'Endpoint', type: 'text', required: true },
    { name: 'auth_method', label: 'Auth method', type: 'text', placeholder: 'HMAC_SHA256' },
    { name: 'api_key_reference', label: 'API key reference', type: 'text' },
    { name: 'poll_window_hours', label: 'Poll window (hours)', type: 'number' },
  ],
};

const KIND_OPTIONS = [
  { value: 'LOCAL_DIRECTORY', label: 'Local directory' },
  { value: 'EMAIL_INBOX', label: 'Email inbox (IMAP)' },
  { value: 'SFTP_CONNECTION', label: 'SFTP connection' },
  { value: 'API_CONNECTION', label: 'API connection' },
];

function toInput(value: unknown, type: FieldType): string {
  if (value === undefined || value === null) return '';
  if (type === 'list') return Array.isArray(value) ? value.join(', ') : String(value);
  return String(value);
}

export function ImportSourceEditor({
  source,
  onClose,
  onSaved,
}: {
  source: ImportSource;
  onClose: () => void;
  onSaved: (updated: ImportSource) => void;
}) {
  const [name, setName] = useState(source.name);
  const [kind, setKind] = useState<ImportSourceKind>(source.kind);
  const [enabled, setEnabled] = useState(source.enabled);
  const [values, setValues] = useState<Record<string, unknown>>({ ...source.connection_json });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [probe, setProbe] = useState<ImportProbeResult | null>(null);
  const [probing, setProbing] = useState(false);

  const specs = CONNECTION_FIELDS[kind];

  const buildConnection = (): Record<string, unknown> => {
    const out: Record<string, unknown> = {};
    for (const spec of specs) {
      const raw = values[spec.name];
      if (spec.type === 'bool') {
        if (raw) out[spec.name] = true;
        continue;
      }
      if (spec.type === 'list') {
        const parts = toInput(raw, 'list')
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
        if (parts.length) out[spec.name] = parts;
        continue;
      }
      const text = toInput(raw, spec.type).trim();
      if (!text) continue;
      out[spec.name] = spec.type === 'number' ? Number(text) : text;
    }
    // Carry through fields the form does not render but the server accepts, so
    // editing a directory never silently drops an existing source_map.
    if (source.connection_json.source_map) out.source_map = source.connection_json.source_map;
    if (source.connection_json.notes) out.notes = source.connection_json.notes;
    return out;
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateImportSource(source.id, {
        name,
        kind,
        enabled,
        connection_json: buildConnection(),
      });
      onSaved(updated);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async () => {
    setProbing(true);
    setError(null);
    try {
      // Save first: a connection test that probed the form rather than the
      // stored configuration would prove nothing about what a run will do.
      const updated = await api.updateImportSource(source.id, {
        name,
        kind,
        enabled,
        connection_json: buildConnection(),
      });
      onSaved(updated);
      setProbe(await api.probeImportSource(source.id));
    } catch (err) {
      setError((err as Error).message);
      setProbe(null);
    } finally {
      setProbing(false);
    }
  };

  return (
    <Dialog
      title={`Import source — ${source.code}`}
      onClose={onClose}
      width={660}
      footer={
        <>
          <button type="button" className="btn" onClick={testConnection} disabled={probing || saving}>
            {probing ? 'Testing…' : 'Save & test connection'}
          </button>
          <button type="button" className="btn btn--primary" onClick={save} disabled={saving || probing}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="btn" onClick={onClose}>
            Close
          </button>
        </>
      }
    >
      {error && <div className="dialog__error">{error}</div>}

      <Field label="Name">
        <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Kind">
        <SelectField
          value={kind}
          options={KIND_OPTIONS}
          onChange={(v) => {
            setKind(v as ImportSourceKind);
            setProbe(null);
          }}
        />
      </Field>
      <Field label="Enabled">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
      </Field>

      <hr style={{ border: 0, borderTop: '1px solid #e2eaf3', margin: '9px 0' }} />

      {specs.map((spec) => (
        <Field
          key={spec.name}
          label={spec.required ? `${spec.label} *` : spec.label}
          note={spec.help}
        >
          {spec.type === 'bool' ? (
            <input
              type="checkbox"
              checked={Boolean(values[spec.name])}
              onChange={(e) => setValues((v) => ({ ...v, [spec.name]: e.target.checked }))}
            />
          ) : (
            <input
              type={spec.type === 'number' ? 'number' : 'text'}
              value={toInput(values[spec.name], spec.type)}
              placeholder={spec.placeholder}
              onChange={(e) => setValues((v) => ({ ...v, [spec.name]: e.target.value }))}
            />
          )}
        </Field>
      ))}

      <div className="callout" style={{ marginTop: 10 }}>
        Files are matched to a data source by name: <span className="mono">&lt;source_id&gt;__&lt;anything&gt;.&lt;ext&gt;</span>,
        e.g. <span className="mono">bank_statement__2026-09-02.csv</span>. A file that does not follow
        this is skipped, and the batch log says which one and why.
      </div>

      {probe && (
        <>
          <div className={probe.files.length ? 'dialog__ok' : 'callout callout--warn'}>
            <strong>{probe.status}</strong> — {probe.location}
            <br />
            {probe.files.length
              ? `${probe.files.length} file(s) ready to import.`
              : 'Connected, but nothing is waiting there right now.'}
          </div>
          {probe.files.length > 0 && (
            <div className="grid-wrap" style={{ marginBottom: 9 }}>
              <table className="grid">
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Data source</th>
                    <th className="num">Bytes</th>
                  </tr>
                </thead>
                <tbody>
                  {probe.files.map((file) => (
                    <tr key={file.filename}>
                      <td className="mono">{file.filename}</td>
                      <td>
                        <Badge value={file.source_id} />
                      </td>
                      <td className="num">{file.size_bytes.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="log" style={{ maxHeight: 150 }}>
            {probe.log.map((line, index) => (
              <div className="log__row" key={index}>
                <span className="log__msg">{line}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </Dialog>
  );
}
