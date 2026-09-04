import { useCallback, useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from '../api/client';
import { Icon } from '../components/Icon';
import { useWorkspace } from '../app/WorkspaceContext';
import type { AgentToolCall, ChatTurn } from '../types';

/** The controller's replies are markdown (headings, bold, tables) -- this
 *  renders it properly instead of showing literal ### / ** / | characters.
 *  A user's own typed message is plain text, never parsed as markdown. */
function TurnBody({ role, content }: { role: string; content: string }) {
  if (role === 'user') return <div className="turn__body">{content}</div>;
  return (
    <div className="turn__body turn__body--markdown">
      <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
    </div>
  );
}

const SUGGESTIONS = [
  'Run the reconciliations for this client',
  'Which batches are still waiting for data?',
  'How did the last reconciliation go?',
  'Why did the last batch fail?',
  'What tax and fee rates are configured here?',
  'What is the cash forecast?',
];

/** Tool names that change system state; shown differently in the trace so an
 *  operator can see at a glance that the agent did something rather than
 *  merely looked something up. */
const ACTION_TOOLS = new Set(['run_batch', 'run_all_batches', 'update_import_source']);

/** What an analyst calls each lookup -- the raw tool name (get_batch_report,
 *  run_batch, ...) is implementation detail and stays hidden until the row
 *  is expanded, same rule as the agent's own text answers (see the "How you
 *  present an answer" section of the backend system prompt). Falls back to a
 *  humanized version of the raw name for any tool not listed here. */
const TOOL_LABELS: Record<string, string> = {
  get_clients: 'Look up clients',
  list_reconciliation_types: 'Reconciliation proof types',
  get_bank_accounts: 'Bank accounts',
  get_account_position: 'Cash by account',
  explain_amount_difference: 'Explain amount difference',
  search_transactions: 'Search transactions',
  aggregate_exceptions: 'Exception totals',
  list_batch_definitions: 'Configured batches',
  get_import_sources: 'Import sources',
  get_batch_log: 'Run log',
  get_batch_report: 'Reconciliation report',
  run_batch: 'Run batch',
  run_all_batches: 'Run all batches',
  update_import_source: 'Update import source',
  get_client_configuration: 'Client configuration',
  get_batches: 'Batches',
  get_batch_status: 'Batch status',
  get_reconciliation_summary: 'Reconciliation summary',
  get_transaction: 'Transaction detail',
  find_transaction_by_reference: 'Find transaction',
  get_match_evidence: 'Match evidence',
  get_exception: 'Exception detail',
  get_exception_summary: 'Exception summary',
  get_tax_rule: 'Tax rule',
  get_tax_calculation: 'Tax calculation',
  get_settlement: 'Settlement detail',
  get_cash_position: 'Cash position',
  get_forecast: 'Cash forecast',
};

function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
}

function ToolTrace({ calls }: { calls: AgentToolCall[] }) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  if (calls.length === 0) return null;

  const toggle = (index: number) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });

  return (
    <div className="turn__tools">
      {calls.map((call, index) => (
        <div className="turn__tool" key={index}>
          <button type="button" onClick={() => toggle(index)}>
            {open.has(index) ? '▾' : '▸'} {ACTION_TOOLS.has(call.tool) ? '⚙ ' : ''}
            {toolLabel(call.tool)}
          </button>
          {open.has(index) && (
            <div className="turn__toolresult">
              <div className="muted small">
                Technical detail — {call.tool}
                {Object.keys(call.input).length > 0 ? `(${Object.keys(call.input).join(', ')})` : '()'}
              </div>
              {JSON.stringify(call.result, null, 2)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ConfirmationCard({
  awaiting,
  onAnswer,
  disabled,
}: {
  awaiting: { action: string; plan: Record<string, unknown>[] };
  onAnswer: (reply: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="confirm">
      <div className="confirm__title">
        Awaiting your confirmation — {awaiting.action.replace(/_/g, ' ')}
      </div>
      <ul className="confirm__plan">
        {awaiting.plan.map((item, index) => (
          <li key={index}>
            <span className="strong">{String(item.code ?? item.import_source_id ?? '—')}</span>
            {item.name ? ` — ${String(item.name)}` : ''}
            {item.state ? (
              <span className="muted"> · {String(item.state).replace(/_/g, ' ').toLowerCase()}</span>
            ) : null}
          </li>
        ))}
      </ul>
      <div className="confirm__actions">
        <button type="button" className="btn btn--primary" disabled={disabled} onClick={() => onAnswer('Yes, go ahead with all of them.')}>
          Yes, run all
        </button>
        {awaiting.plan.length > 1 && (
          <button
            type="button"
            className="btn"
            disabled={disabled}
            onClick={() => onAnswer(`Just ${String(awaiting.plan[0]?.code ?? 'the first one')}, please.`)}
          >
            Only {String(awaiting.plan[0]?.code ?? 'the first')}
          </button>
        )}
        <button type="button" className="btn" disabled={disabled} onClick={() => onAnswer('No, do not run anything.')}>
          Cancel
        </button>
      </div>
    </div>
  );
}

export function AgentPanel() {
  const { activeBlotter, clientById, openBlotter, refresh, clients } = useWorkspace();
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [width, setWidth] = useState(360);
  const logRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);

  // The agent is scoped to whatever window has focus; with a single client
  // configured there is nothing ambiguous to scope to, so it follows that one.
  const scopedClientId = activeBlotter?.clientId ?? (clients.length === 1 ? clients[0].id : null);
  const scopedClient = scopedClientId ? clientById(scopedClientId) : undefined;

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns, sending]);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || sending) return;

      const history: ChatTurn[] = [...turns, { role: 'user', content: trimmed }];
      setTurns(history);
      setInput('');
      setSending(true);

      try {
        const response = await api.chat(history, scopedClientId);
        setTurns([
          ...history,
          {
            role: 'assistant',
            content: response.text,
            toolCalls: response.tool_calls,
            awaiting: response.awaiting_confirmation,
            error: !response.configured,
          },
        ]);

        // The agent acted: bring the operator to what it touched, and re-read
        // any open window so the screen agrees with what it just said.
        if (response.ui_hint?.client_id) {
          const hintClient = clientById(response.ui_hint.client_id);
          if (response.ui_hint.batch_id) {
            openBlotter({
              kind: 'batch',
              clientId: response.ui_hint.client_id,
              batchId: response.ui_hint.batch_id,
              title: 'Batch run',
              subtitle: 'started by the agent',
            });
          } else if (response.ui_hint.open === 'reconciliation') {
            openBlotter({
              kind: 'recon',
              clientId: response.ui_hint.client_id,
              title: 'Reconciliation Management',
              subtitle: hintClient ? `${hintClient.name} (${hintClient.code})` : undefined,
            });
          }
        }
        if (response.tool_calls.some((call) => ACTION_TOOLS.has(call.tool))) refresh();
      } catch (err) {
        setTurns([
          ...history,
          { role: 'assistant', content: (err as Error).message, error: true },
        ]);
      } finally {
        setSending(false);
      }
    },
    [turns, sending, scopedClientId, clientById, openBlotter, refresh],
  );

  // Drag-to-resize, the way a docked tool panel behaves.
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current) return;
      const next = window.innerWidth - e.clientX;
      setWidth(Math.max(260, Math.min(640, next)));
    };
    const onUp = () => {
      draggingRef.current = false;
      document.body.style.cursor = '';
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  const lastTurn = turns[turns.length - 1];
  const pendingConfirmation = lastTurn?.role === 'assistant' ? lastTurn.awaiting : null;

  return (
    <>
      <div
        className="agent__grip"
        onMouseDown={() => {
          draggingRef.current = true;
          document.body.style.cursor = 'col-resize';
        }}
        role="separator"
        aria-orientation="vertical"
      />
      <aside className="agent" style={{ width }}>
        <div className="agent__header">
          <Icon name="agent" size={14} />
          <span>AI Finance Controller</span>
          <span className="blotter__spacer" />
          <span className="agent__scope">
            {scopedClient ? scopedClient.code : 'all clients'}
          </span>
        </div>

        <div className="agent__log" ref={logRef}>
          {turns.length === 0 && (
            <div className="agent__empty">
              I can explain what the system did and operate it for you. Everything I state comes from
              a tool call against the live database — I have no memory of your data.
              <br />
              <br />
              Anything that changes state asks you first.
              <ul>
                {SUGGESTIONS.map((suggestion) => (
                  <li key={suggestion} onClick={() => send(suggestion)}>
                    {suggestion}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {turns.map((turn, index) => (
            <div
              key={index}
              className={`turn turn--${turn.role}${turn.error ? ' turn--error' : ''}`}
            >
              <div className="turn__role">{turn.role === 'user' ? 'You' : 'Controller'}</div>
              <TurnBody role={turn.role} content={turn.content} />
              {turn.toolCalls && <ToolTrace calls={turn.toolCalls} />}
            </div>
          ))}

          {pendingConfirmation && (
            <ConfirmationCard awaiting={pendingConfirmation} onAnswer={send} disabled={sending} />
          )}

          {sending && (
            <div className="turn">
              <div className="turn__role">Controller</div>
              <div className="turn__body">
                <span className="spinner" /> Working…
              </div>
            </div>
          )}
        </div>

        <div className="agent__composer">
          <textarea
            value={input}
            placeholder={
              scopedClient
                ? `Ask about ${scopedClient.code}, or tell me to run its batches…`
                : 'Open a window to scope me to a client, or ask a general question…'
            }
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
          />
          <div className="agent__composer-row">
            <span className="agent__hint">Enter to send · Shift+Enter for a new line</span>
            <button type="button" className="btn" onClick={() => setTurns([])} disabled={turns.length === 0}>
              Clear
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => send(input)}
              disabled={sending || !input.trim()}
            >
              Send
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
