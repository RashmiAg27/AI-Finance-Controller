import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Icon } from '../components/Icon';
import { Badge, Grid, Pane } from '../components/Office';
import { useLoader, useRibbonCommands, useWorkspace, type Blotter } from '../app/WorkspaceContext';
import type { DataSourceConfig, IdentifierLinkage, MatchingRule } from '../types';

const DATA_TYPES = ['string', 'date', 'decimal'];
const SIGN_CONVENTIONS = ['', 'signed', 'debit_negative', 'credit_positive'];

/**
 * The Matching Rules window is where a client's own field names are mapped
 * onto this system's canonical vocabulary. Two things it deliberately makes
 * visible rather than hiding:
 *
 *  - an identifier mapping is only half the story; two identifier types are
 *    never treated as the same reference unless an identifier_linkage rule
 *    says so, and each such rule carries the rationale for why;
 *  - the pass number a rule runs in decides what evidence it is allowed to
 *    use, so it is shown alongside the rule rather than buried.
 */
export function MatchingRulesBlotter({ blotter }: { blotter: Blotter }) {
  const { revision, refresh, clientById, setStatus } = useWorkspace();
  const clientId = blotter.clientId;
  const client = clientById(clientId);

  const loaded = useLoader(() => api.matchingConfig(clientId), [clientId, revision]);
  const [sources, setSources] = useState<DataSourceConfig[]>([]);
  const [rules, setRules] = useState<MatchingRule[]>([]);
  const [linkage, setLinkage] = useState<IdentifierLinkage[]>([]);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const view = loaded.data?.data;
    if (!view) return;
    setSources(structuredClone(view.data_sources));
    setRules(structuredClone(view.matching_rules));
    setLinkage(structuredClone(view.identifier_linkage));
    setDirty(false);
  }, [loaded.data]);

  const view = loaded.data?.data;
  const canonicalFields = view?.canonical_fields ?? [];

  const updateSources = (mutate: (draft: DataSourceConfig[]) => void) => {
    setSources((current) => {
      const next = structuredClone(current);
      mutate(next);
      return next;
    });
    setDirty(true);
    setNotice(null);
  };

  const updateRules = (mutate: (draft: MatchingRule[]) => void) => {
    setRules((current) => {
      const next = structuredClone(current);
      mutate(next);
      return next;
    });
    setDirty(true);
    setNotice(null);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const result = await api.saveMatchingConfig(clientId, {
        data_sources: sources,
        matching_rules: rules,
        identifier_linkage: linkage,
      });
      setNotice(
        `Saved as configuration version ${result.config_version}. The next run of any batch for ` +
          'this client uses it.',
      );
      setStatus(`Matching configuration saved (v${result.config_version}).`);
      setDirty(false);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const revert = () => {
    if (view) {
      setSources(structuredClone(view.data_sources));
      setRules(structuredClone(view.matching_rules));
      setLinkage(structuredClone(view.identifier_linkage));
    }
    setDirty(false);
    setNotice(null);
  };

  useRibbonCommands(blotter.id, [
    { id: 'save', group: 'Configuration', label: 'Save as new version', primary: true,
      disabled: !dirty || saving, run: save },
    { id: 'revert', group: 'Configuration', label: 'Revert changes', disabled: !dirty, run: revert },
  ]);

  return (
    <div className="blotter">
      <header className="blotter__header">
        <Icon name="rules" size={18} />
        <span className="blotter__title">Matching Rules &amp; Field Mapping</span>
        <span className="blotter__subtitle">
          {client ? `${client.name} (${client.code})` : clientId}
          {view ? ` · configuration v${view.config_version}` : ''}
        </span>
        <span className="blotter__spacer" />
        {dirty && <span className="badge badge--warn">unsaved changes</span>}
      </header>

      <div className="toolbar">
        <button type="button" className="btn btn--primary" onClick={save} disabled={!dirty || saving}>
          <Icon name="save" size={12} /> {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          className="btn"
          disabled={!dirty}
          onClick={() => {
            if (view) {
              setSources(structuredClone(view.data_sources));
              setRules(structuredClone(view.matching_rules));
              setLinkage(structuredClone(view.identifier_linkage));
            }
            setDirty(false);
            setNotice(null);
          }}
        >
          <Icon name="undo" size={12} /> Revert
        </button>
        <span className="toolbar__spacer" />
        <button type="button" className="btn" onClick={refresh}>
          <Icon name="refresh" size={12} /> Refresh
        </button>
      </div>

      <div className="blotter__body">
        {loaded.error && <div className="callout callout--error">{loaded.error}</div>}
        {error && <div className="callout callout--error">{error}</div>}
        {notice && <div className="callout">{notice}</div>}

        <div className="callout">
          Each client sends its own column names; this is where they are mapped onto the canonical
          fields the engine understands. Mapping a column to <span className="mono">identifier</span>{' '}
          also requires an identifier type — and two identifier types are still never treated as the
          same reference until a linkage rule below says they are.
        </div>

        {sources.map((source, sourceIndex) => (
          <Pane
            key={source.source_id}
            title={`${source.source_id}`}
            hint={`${source.role.toLowerCase()} · ${source.file_format}${
              source.sheet_name ? ` · sheet "${source.sheet_name}"` : ''
            } · ${source.field_mappings.length} field mappings`}
            flush
            defaultOpen={sourceIndex < 2}
          >
            <Grid
              columns={[
                { key: 'source_field', label: 'Their field' },
                { key: 'canonical', label: 'Our canonical field' },
                { key: 'identifier', label: 'Identifier type' },
                { key: 'type', label: 'Data type' },
                { key: 'format', label: 'Date format' },
                { key: 'sign', label: 'Sign convention' },
                { key: 'required', label: 'Req.', width: 40 },
              ]}
              empty="No field mappings."
            >
              {source.field_mappings.map((mapping, mappingIndex) => (
                <tr key={`${mapping.source_field}-${mappingIndex}`}>
                  <td>
                    <input
                      type="text"
                      value={mapping.source_field}
                      onChange={(e) =>
                        updateSources((draft) => {
                          draft[sourceIndex].field_mappings[mappingIndex].source_field = e.target.value;
                        })
                      }
                    />
                  </td>
                  <td>
                    <select
                      value={mapping.canonical_field}
                      onChange={(e) =>
                        updateSources((draft) => {
                          draft[sourceIndex].field_mappings[mappingIndex].canonical_field = e.target.value;
                        })
                      }
                    >
                      {canonicalFields.map((f) => (
                        <option key={f} value={f}>
                          {f}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      type="text"
                      value={mapping.identifier_type ?? ''}
                      placeholder={mapping.canonical_field === 'identifier' ? 'required' : '—'}
                      disabled={mapping.canonical_field !== 'identifier'}
                      onChange={(e) =>
                        updateSources((draft) => {
                          draft[sourceIndex].field_mappings[mappingIndex].identifier_type =
                            e.target.value || null;
                        })
                      }
                    />
                  </td>
                  <td>
                    <select
                      value={mapping.data_type}
                      onChange={(e) =>
                        updateSources((draft) => {
                          draft[sourceIndex].field_mappings[mappingIndex].data_type = e.target.value;
                        })
                      }
                    >
                      {DATA_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      type="text"
                      value={mapping.date_format ?? ''}
                      placeholder={mapping.data_type === 'date' ? '%Y-%m-%d' : '—'}
                      disabled={mapping.data_type !== 'date'}
                      onChange={(e) =>
                        updateSources((draft) => {
                          draft[sourceIndex].field_mappings[mappingIndex].date_format =
                            e.target.value || null;
                        })
                      }
                    />
                  </td>
                  <td>
                    <select
                      value={mapping.sign_convention ?? ''}
                      disabled={mapping.canonical_field !== 'amount'}
                      onChange={(e) =>
                        updateSources((draft) => {
                          draft[sourceIndex].field_mappings[mappingIndex].sign_convention =
                            e.target.value || null;
                        })
                      }
                    >
                      {SIGN_CONVENTIONS.map((s) => (
                        <option key={s} value={s}>
                          {s || '—'}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      checked={mapping.required}
                      onChange={(e) =>
                        updateSources((draft) => {
                          draft[sourceIndex].field_mappings[mappingIndex].required = e.target.checked;
                        })
                      }
                    />
                  </td>
                </tr>
              ))}
            </Grid>
            <div className="pane__body">
              <div className="small">
                <strong>Identifier priority:</strong>{' '}
                <span className="mono">{source.identifier_priority.join(' → ') || '—'}</span>
                {'  ·  '}
                <strong>Static fields:</strong>{' '}
                <span className="mono">
                  {Object.entries(source.static_fields)
                    .map(([k, v]) => `${k}=${v}`)
                    .join(', ') || '—'}
                </span>
              </div>
            </div>
          </Pane>
        ))}

        <Pane
          title="Identifier linkage"
          hint="The only thing that can declare two identifier types equivalent"
          flush
        >
          <Grid
            columns={[
              { key: 'source', label: 'From' },
              { key: 'target', label: 'To' },
              { key: 'type', label: 'Linkage' },
              { key: 'confidence', label: 'Conf.', numeric: true },
              { key: 'rationale', label: 'Why this is true for this client' },
            ]}
            empty="No linkage rules: nothing will match on reference."
          >
            {linkage.map((rule) => (
              <tr key={rule.rule_id}>
                <td className="mono">{rule.source_identifier_type}</td>
                <td className="mono">{rule.target_identifier_type}</td>
                <td>
                  <Badge value={rule.linkage_type} />
                </td>
                <td className="num">{rule.confidence}</td>
                <td>{rule.rationale}</td>
              </tr>
            ))}
          </Grid>
        </Pane>

        <Pane title="Matching rules" hint={`${rules.length} rules across the deterministic passes`} flush>
          <Grid
            columns={[
              { key: 'rule', label: 'Rule' },
              { key: 'pass', label: 'Pass', numeric: true, width: 50 },
              { key: 'on', label: 'Matches on' },
              { key: 'conditions', label: 'Conditions' },
              { key: 'confidence', label: 'Confidence', numeric: true },
            ]}
            empty="No matching rules configured."
          >
            {rules.map((rule, index) => (
              <tr key={rule.rule_id}>
                <td className="mono">{rule.rule_id}</td>
                <td className="num">{rule.pass}</td>
                <td className="small">
                  {rule.match_on.length === 0 ? (
                    <span className="muted">amount / date / counterparty</span>
                  ) : (
                    rule.match_on.map((condition, conditionIndex) => (
                      <div key={conditionIndex} className="mono">
                        {condition.left_identifier} ↔ {condition.right_identifier} ({condition.comparison})
                      </div>
                    ))
                  )}
                </td>
                <td className="small">
                  {rule.conditions ? (
                    Object.entries(rule.conditions).map(([key, value]) => (
                      <div key={key}>
                        {key}: <span className="mono">{JSON.stringify(value)}</span>
                      </div>
                    ))
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td className="num">
                  <input
                    type="number"
                    step="0.05"
                    min={0}
                    max={1}
                    value={rule.confidence}
                    onChange={(e) =>
                      updateRules((draft) => {
                        draft[index].confidence = Number(e.target.value);
                      })
                    }
                  />
                </td>
              </tr>
            ))}
          </Grid>
        </Pane>

        {view?.aggregation_rules && (
          <Pane title="Aggregation (1:N and N:1)" defaultOpen={false}>
            <div className="small">
              Groups still-unmatched transactions sharing{' '}
              <span className="mono">{String(view.aggregation_rules.identifier_type)}</span> and compares
              the groups' sums. That identifier is deliberately excluded from every pass 1/2 rule above,
              so those passes cannot consume the transactions before grouping can happen.
              <pre className="mono" style={{ whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(view.aggregation_rules, null, 2)}
              </pre>
            </div>
          </Pane>
        )}
      </div>
    </div>
  );
}
