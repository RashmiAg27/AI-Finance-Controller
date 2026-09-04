import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Icon } from '../components/Icon';
import { Badge, Field, Grid, Pane } from '../components/Office';
import { useLoader, useRibbonCommands, useWorkspace, type Blotter } from '../app/WorkspaceContext';
import type { StatutoryCharge, TaxFeeRules } from '../types';

const VERIFICATION_OPTIONS = ['VERIFIED', 'NOT_VERIFIED', 'PROTOTYPE_ASSUMPTION'];
const BASIS_OPTIONS: StatutoryCharge['basis'][] = ['GROSS', 'FEE', 'FEE_PLUS_TAX'];

const EMPTY_CHARGE: StatutoryCharge = {
  code: 'NEW_CHARGE',
  label: 'New charge',
  basis: 'GROSS',
  rate_percent: 0,
  flat_amount: 0,
  applies_to_instrument_types: [],
  enabled: true,
  source_authority: null,
  source_reference: null,
  verification_status: 'NOT_VERIFIED',
  note: null,
};

export function TaxBlotter({ blotter }: { blotter: Blotter }) {
  const { revision, refresh, clientById, setStatus } = useWorkspace();
  const clientId = blotter.clientId;
  const client = clientById(clientId);

  const loaded = useLoader(() => api.taxConfig(clientId), [clientId, revision]);
  const [draft, setDraft] = useState<TaxFeeRules | null>(null);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (loaded.data?.data.tax_fee_rules) {
      setDraft(structuredClone(loaded.data.data.tax_fee_rules));
      setDirty(false);
    }
  }, [loaded.data]);

  const update = (mutate: (rules: TaxFeeRules) => void) => {
    setDraft((current) => {
      if (!current) return current;
      const next = structuredClone(current);
      mutate(next);
      return next;
    });
    setDirty(true);
    setNotice(null);
  };

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const result = await api.saveTaxConfig(clientId, { tax_fee_rules: draft });
      setNotice(
        `Saved as configuration version ${result.config_version}. It applies to the next run; ` +
          'runs already in flight keep the version they started with.',
      );
      setStatus(`Tax configuration saved (v${result.config_version}).`);
      setDirty(false);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const view = loaded.data?.data;

  const revert = () => {
    if (loaded.data?.data.tax_fee_rules) setDraft(structuredClone(loaded.data.data.tax_fee_rules));
    setDirty(false);
    setNotice(null);
  };

  useRibbonCommands(blotter.id, [
    { id: 'save', group: 'Configuration', label: 'Save as new version', primary: true,
      disabled: !draft || !dirty || saving, run: save },
    { id: 'revert', group: 'Configuration', label: 'Revert changes',
      disabled: !dirty, run: revert },
    { id: 'add-charge', group: 'Statutory charges', label: 'Add charge',
      disabled: !draft,
      run: () => update((r) => { r.statutory_charges.push(structuredClone(EMPTY_CHARGE)); }) },
  ]);

  return (
    <div className="blotter">
      <header className="blotter__header">
        <Icon name="tax" size={16} />
        <span className="blotter__title">Tax, Fee &amp; Commission Rules</span>
        <span className="blotter__subtitle">
          {client ? `${client.name} (${client.code})` : clientId}
          {view ? ` · configuration v${view.config_version}` : ''}
        </span>
        <span className="blotter__spacer" />
        {dirty && <span className="badge badge--warn">unsaved changes</span>}
      </header>

      <div className="toolbar">
        <button type="button" className="btn btn--primary" onClick={save} disabled={!draft || !dirty || saving}>
          <Icon name="save" size={12} /> {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          className="btn"
          disabled={!dirty}
          onClick={() => {
            if (loaded.data?.data.tax_fee_rules) setDraft(structuredClone(loaded.data.data.tax_fee_rules));
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

        {view && !view.configured && (
          <div className="callout callout--warn">
            This client has no tax/fee treatment configured. Discrepancies between a gross internal
            amount and a net external amount will go straight to the exception queue.
          </div>
        )}

        {draft && (
          <>
            <div className="callout">
              These rates are applied for real: they decide which settlements reconcile and how a
              settlement is decomposed. <strong>Verification status is shown on every rate</strong> — an
              unverified figure is illustrative and must be replaced with the client's own before
              anyone relies on it.
            </div>

            <Pane title="Applicability" hint="Which instrument pairing this treatment covers">
              <Field label="Internal instrument">
                <input
                  type="text"
                  value={draft.applicable_when.internal_instrument_type}
                  onChange={(e) =>
                    update((r) => {
                      r.applicable_when.internal_instrument_type = e.target.value;
                    })
                  }
                />
              </Field>
              <Field label="External instrument">
                <input
                  type="text"
                  value={draft.applicable_when.external_instrument_type}
                  onChange={(e) =>
                    update((r) => {
                      r.applicable_when.external_instrument_type = e.target.value;
                    })
                  }
                />
              </Field>
              <Field label="Rounding tolerance" note="How far the computed net may differ from the observed net and still count as explained.">
                <input
                  type="number"
                  step="0.01"
                  value={draft.rounding_tolerance}
                  onChange={(e) =>
                    update((r) => {
                      r.rounding_tolerance = Number(e.target.value);
                    })
                  }
                />
              </Field>
              <Field label="Date field">
                <select
                  value={draft.date_field}
                  onChange={(e) =>
                    update((r) => {
                      r.date_field = e.target.value;
                    })
                  }
                >
                  <option value="transaction_date">transaction_date</option>
                  <option value="value_date">value_date</option>
                  <option value="settlement_date">settlement_date</option>
                </select>
              </Field>
              <Field label="Date tolerance (days)">
                <input
                  type="number"
                  value={draft.date_tolerance_days}
                  onChange={(e) =>
                    update((r) => {
                      r.date_tolerance_days = Number(e.target.value);
                    })
                  }
                />
              </Field>
            </Pane>

            <Pane title="Processing fee" hint="Commercial rate — MDR, brokerage, or equivalent">
              <Field label="Rate (%)">
                <input
                  type="number"
                  step="0.001"
                  value={draft.fee.rate_percent}
                  onChange={(e) =>
                    update((r) => {
                      r.fee.rate_percent = Number(e.target.value);
                    })
                  }
                />
              </Field>
              <Field label="Verification">
                <select
                  value={draft.fee.verification_status}
                  onChange={(e) =>
                    update((r) => {
                      r.fee.verification_status = e.target.value;
                    })
                  }
                >
                  {VERIFICATION_OPTIONS.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Note">
                <textarea
                  rows={3}
                  style={{ width: '100%' }}
                  value={draft.fee.note ?? ''}
                  onChange={(e) =>
                    update((r) => {
                      r.fee.note = e.target.value || null;
                    })
                  }
                />
              </Field>
            </Pane>

            <Pane title="Tax on fee" hint="Sourced from a versioned TaxRule, never entered as a bare rate">
              <Field
                label="Tax rule id"
                note="The rate, authority, source reference and verification status all come from this rule."
              >
                <input
                  type="text"
                  value={draft.tax_on_fee.tax_rule_id}
                  onChange={(e) =>
                    update((r) => {
                      r.tax_on_fee.tax_rule_id = e.target.value;
                    })
                  }
                />
              </Field>
            </Pane>

            <Pane title="Commission" hint={draft.commission ? draft.commission.label : 'not configured'}>
              {draft.commission ? (
                <>
                  <Field label="Label">
                    <input
                      type="text"
                      value={draft.commission.label}
                      onChange={(e) =>
                        update((r) => {
                          r.commission!.label = e.target.value;
                        })
                      }
                    />
                  </Field>
                  <Field label="Rate (%)">
                    <input
                      type="number"
                      step="0.001"
                      value={draft.commission.rate_percent}
                      onChange={(e) =>
                        update((r) => {
                          r.commission!.rate_percent = Number(e.target.value);
                        })
                      }
                    />
                  </Field>
                  <Field label="Minimum amount">
                    <input
                      type="number"
                      step="0.01"
                      value={draft.commission.minimum_amount}
                      onChange={(e) =>
                        update((r) => {
                          r.commission!.minimum_amount = Number(e.target.value);
                        })
                      }
                    />
                  </Field>
                  <Field label="Maximum amount" note="Leave blank for no cap.">
                    <input
                      type="number"
                      step="0.01"
                      value={draft.commission.maximum_amount ?? ''}
                      onChange={(e) =>
                        update((r) => {
                          r.commission!.maximum_amount = e.target.value === '' ? null : Number(e.target.value);
                        })
                      }
                    />
                  </Field>
                  <Field label="Verification">
                    <select
                      value={draft.commission.verification_status}
                      onChange={(e) =>
                        update((r) => {
                          r.commission!.verification_status = e.target.value;
                        })
                      }
                    >
                      {VERIFICATION_OPTIONS.map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <button
                    type="button"
                    className="btn"
                    onClick={() =>
                      update((r) => {
                        r.commission = null;
                      })
                    }
                  >
                    Remove commission
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="btn"
                  onClick={() =>
                    update((r) => {
                      r.commission = {
                        label: 'Commission',
                        rate_percent: 0,
                        minimum_amount: 0,
                        maximum_amount: null,
                        verification_status: 'PROTOTYPE_ASSUMPTION',
                        note: null,
                      };
                    })
                  }
                >
                  Add commission
                </button>
              )}
            </Pane>

            <Pane
              title="Statutory charges"
              hint={`${draft.statutory_charges.length} configured — deducted alongside the fee`}
              flush
              actions={
                <button
                  type="button"
                  className="btn"
                  onClick={() =>
                    update((r) => {
                      r.statutory_charges.push(structuredClone(EMPTY_CHARGE));
                    })
                  }
                >
                  Add charge
                </button>
              }
            >
              <Grid
                columns={[
                  { key: 'on', label: 'On', width: 34 },
                  { key: 'code', label: 'Code' },
                  { key: 'label', label: 'Label' },
                  { key: 'basis', label: 'Basis' },
                  { key: 'rate', label: 'Rate %', numeric: true },
                  { key: 'flat', label: 'Flat', numeric: true },
                  { key: 'verification', label: 'Verification' },
                  { key: 'source', label: 'Source reference' },
                  { key: 'del', label: '', width: 32 },
                ]}
                empty="No statutory charges configured."
              >
                {draft.statutory_charges.map((charge, index) => (
                  <tr key={index}>
                    <td>
                      <input
                        type="checkbox"
                        checked={charge.enabled}
                        onChange={(e) =>
                          update((r) => {
                            r.statutory_charges[index].enabled = e.target.checked;
                          })
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        value={charge.code}
                        onChange={(e) =>
                          update((r) => {
                            r.statutory_charges[index].code = e.target.value;
                          })
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        value={charge.label}
                        onChange={(e) =>
                          update((r) => {
                            r.statutory_charges[index].label = e.target.value;
                          })
                        }
                      />
                    </td>
                    <td>
                      <select
                        value={charge.basis}
                        onChange={(e) =>
                          update((r) => {
                            r.statutory_charges[index].basis = e.target.value as StatutoryCharge['basis'];
                          })
                        }
                      >
                        {BASIS_OPTIONS.map((b) => (
                          <option key={b} value={b}>
                            {b}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="num">
                      <input
                        type="number"
                        step="0.00001"
                        value={charge.rate_percent}
                        onChange={(e) =>
                          update((r) => {
                            r.statutory_charges[index].rate_percent = Number(e.target.value);
                          })
                        }
                      />
                    </td>
                    <td className="num">
                      <input
                        type="number"
                        step="0.01"
                        value={charge.flat_amount}
                        onChange={(e) =>
                          update((r) => {
                            r.statutory_charges[index].flat_amount = Number(e.target.value);
                          })
                        }
                      />
                    </td>
                    <td>
                      <select
                        value={charge.verification_status}
                        onChange={(e) =>
                          update((r) => {
                            r.statutory_charges[index].verification_status = e.target.value;
                          })
                        }
                      >
                        {VERIFICATION_OPTIONS.map((v) => (
                          <option key={v} value={v}>
                            {v}
                          </option>
                        ))}
                      </select>
                      <div style={{ marginTop: 2 }}>
                        <Badge value={charge.verification_status} />
                      </div>
                    </td>
                    <td>
                      <input
                        type="text"
                        value={charge.source_reference ?? ''}
                        placeholder="Act / notification / schedule"
                        onChange={(e) =>
                          update((r) => {
                            r.statutory_charges[index].source_reference = e.target.value || null;
                          })
                        }
                      />
                      {charge.note && <div className="muted small">{charge.note}</div>}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn"
                        title="Remove this charge"
                        onClick={() =>
                          update((r) => {
                            r.statutory_charges.splice(index, 1);
                          })
                        }
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
              </Grid>
            </Pane>
          </>
        )}
      </div>
    </div>
  );
}
