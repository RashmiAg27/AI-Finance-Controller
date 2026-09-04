import { useEffect, useState } from 'react';
import { Icon } from '../components/Icon';
import { RibbonButton, RibbonGroup, RibbonStack } from '../components/Office';
import { useWorkspace, type BlotterKind } from './WorkspaceContext';

/* --------------------------------------------------------------------------
   Which window each ribbon tab opens, and what it is called once open.
   -------------------------------------------------------------------------- */

const WINDOWS: Record<
  BlotterKind,
  { tab: string; title: string; icon: Parameters<typeof Icon>[0]['name']; description: string }
> = {
  recon: {
    tab: 'Reconciliation',
    title: 'Reconciliation Management',
    icon: 'recon',
    description: 'Match transactions and review unmatched entries.',
  },
  sources: {
    tab: 'Data Sources',
    title: 'Data Sources & Accounts',
    icon: 'connect',
    description: 'Manage bank accounts and incoming transaction data.',
  },
  tax: {
    tab: 'Tax & Fees',
    title: 'Tax, Fee & Commission Rules',
    icon: 'tax',
    description: 'Manage taxes, fees, and settlement charges.',
  },
  matching: {
    tab: 'Matching Rules',
    title: 'Matching Rules & Field Mapping',
    icon: 'rules',
    description: 'Configure rules used to match transactions.',
  },
  forecast: {
    tab: 'Cash Forecast',
    title: 'Cash Position & Forecast',
    icon: 'forecast',
    description: 'Forecast cash inflows, outflows, and balances.',
  },
  exceptions: {
    tab: 'Exceptions',
    title: 'Exception Queue',
    icon: 'exception',
    description: 'Review and resolve unmatched or problematic entries.',
  },
  batch: { tab: 'Batch', title: 'Batch Run', icon: 'log', description: '' },
};

// Ordered the way money travels: what arrives, what proves it, what it cost,
// what broke, and what is left. This is the primary set of tools in the
// ribbon -- there is no separate tab strip above it any more.
const RIBBON_TOOLS: BlotterKind[] = [
  'recon',
  'sources',
  'tax',
  'matching',
  'exceptions',
  'forecast',
];

/* --------------------------------------------------------------------------
   Client picker -- an inline dropdown anchored under the ribbon, not a modal.
   One tool click either opens straight to the only client there is, or drops
   this panel to ask which one -- there is no separate "Open for..." step.
   -------------------------------------------------------------------------- */

function ToolClientPicker({
  kind,
  onCancel,
  onPick,
}: {
  kind: BlotterKind;
  onCancel: () => void;
  onPick: (clientId: string) => void;
}) {
  const { clients, loadingClients, clientsError } = useWorkspace();
  const meta = WINDOWS[kind];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  return (
    <>
      <div className="tool-picker__backdrop" onMouseDown={onCancel} />
      <div className="tool-picker" role="dialog" aria-label={`Open ${meta.title} for…`}>
        <div className="tool-picker__title">
          <span className="blotter__spacer">{meta.tab} — choose a client</span>
          <button type="button" className="doctab__close" onClick={onCancel} aria-label="Cancel">
            ✕
          </button>
        </div>
        <div className="tool-picker__body">
          {clientsError && <div className="dialog__error">{clientsError}</div>}
          {loadingClients && <div className="muted">Loading clients…</div>}
          {!loadingClients && !clientsError && clients.length === 0 && (
            <div className="muted">
              No clients. Seed the demo world with{' '}
              <span className="mono">python scripts/seed_demo_world.py --run</span>.
            </div>
          )}
          {clients.map((client) => (
            <button
              key={client.id}
              type="button"
              className="tool-picker__item"
              onClick={() => onPick(client.id)}
            >
              <span className="strong">{client.name}</span>
              <span className="muted small">
                {client.code} · {client.status}
              </span>
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

/* --------------------------------------------------------------------------
   Title bar
   -------------------------------------------------------------------------- */

export function TitleBar() {
  const { activeBlotter, clientById, refresh, blotters, closeAll } = useWorkspace();
  const client = activeBlotter ? clientById(activeBlotter.clientId) : undefined;

  return (
    <div className="titlebar">
      <div className="orb" title="AI Finance Controller">
        AFC
      </div>
      <div className="qat">
        <button type="button" title="Refresh all open windows" onClick={refresh}>
          <Icon name="refresh" size={14} />
        </button>
        <button
          type="button"
          title="Close all windows"
          onClick={closeAll}
          disabled={blotters.length === 0}
        >
          <Icon name="close" size={12} />
        </button>
      </div>
      <div className="titlebar__caption">
        {activeBlotter ? (
          <>
            <span className="titlebar__client">{client ? client.name : activeBlotter.clientId}</span>
            {' — '}
            {activeBlotter.title}
          </>
        ) : (
          'AI Finance Controller'
        )}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------
   Ribbon
   -------------------------------------------------------------------------- */

export function Ribbon() {
  const { openBlotter, activeBlotter, clientById, refresh, closeBlotter, clients, commands } =
    useWorkspace();
  const [picking, setPicking] = useState<BlotterKind | null>(null);

  const openFor = (kind: BlotterKind, clientId: string) => {
    const client = clientById(clientId);
    openBlotter({
      kind,
      clientId,
      title: WINDOWS[kind].title,
      subtitle: client ? `${client.name} (${client.code})` : clientId,
    });
    setPicking(null);
  };

  // A ribbon tool opens straight to the workspace: skip the picker when
  // there is only one client to choose (nothing to choose), and skip it too
  // if the picker for this same tool is already open (a second click closes
  // it, same as any other dropdown).
  const requestOpen = (kind: BlotterKind) => {
    if (clients.length === 1) {
      openFor(kind, clients[0].id);
      return;
    }
    setPicking((current) => (current === kind ? null : kind));
  };

  // Commands published by the currently focused document tab, in the order
  // it published them, bucketed under its own group headings. These are
  // contextual to whichever window is open, not to a ribbon tool selection --
  // there is no separate "selected tool" state to match against any more.
  const commandGroups: [string, typeof commands][] = [];
  if (activeBlotter) {
    for (const command of commands) {
      const bucket = commandGroups.find(([name]) => name === command.group);
      if (bucket) bucket[1].push(command);
      else commandGroups.push([command.group, [command]]);
    }
  }

  return (
    <div className="ribbon">
      <div className="ribbon__body">
        <RibbonGroup label="Open">
          {RIBBON_TOOLS.map((kind) => (
            <RibbonButton
              key={kind}
              icon={WINDOWS[kind].icon}
              label={WINDOWS[kind].tab}
              onClick={() => requestOpen(kind)}
              description={WINDOWS[kind].description}
            />
          ))}
        </RibbonGroup>

        {activeBlotter ? (
          commandGroups.map(([groupName, groupCommands]) => (
            <RibbonGroup key={groupName} label={groupName}>
              <RibbonStack>
                {groupCommands.map((command) => (
                  <button
                    key={command.id}
                    type="button"
                    className={`rbtn rbtn--small${command.primary ? ' rbtn--primary' : ''}`}
                    onClick={command.run}
                    disabled={command.disabled}
                    title={command.title ?? command.label}
                  >
                    <span className="rbtn__label">{command.label}</span>
                  </button>
                ))}
              </RibbonStack>
            </RibbonGroup>
          ))
        ) : (
          <RibbonGroup label="Getting started">
            <div className="rinfo muted">Pick a tool above, choose a client, and its workspace opens here.</div>
          </RibbonGroup>
        )}

        <RibbonGroup label="View">
          <RibbonStack>
            <button type="button" className="rbtn rbtn--small" onClick={refresh}>
              <span className="rbtn__label">Refresh all</span>
            </button>
            <button
              type="button"
              className="rbtn rbtn--small"
              disabled={!activeBlotter}
              onClick={() => activeBlotter && closeBlotter(activeBlotter.id)}
            >
              <span className="rbtn__label">Close window</span>
            </button>
          </RibbonStack>
        </RibbonGroup>
      </div>

      {picking && (
        <ToolClientPicker
          kind={picking}
          onCancel={() => setPicking(null)}
          onPick={(clientId) => openFor(picking, clientId)}
        />
      )}
    </div>
  );
}

/* --------------------------------------------------------------------------
   Document tabs + status bar
   -------------------------------------------------------------------------- */

export function DocumentTabs() {
  const { blotters, activeId, focusBlotter, closeBlotter, clientById } = useWorkspace();
  if (blotters.length === 0) return null;

  return (
    <div className="doctabs" role="tablist">
      {blotters.map((blotter) => {
        const client = clientById(blotter.clientId);
        return (
          <div
            key={blotter.id}
            role="tab"
            aria-selected={blotter.id === activeId}
            className={`doctab${blotter.id === activeId ? ' is-active' : ''}`}
            onClick={() => focusBlotter(blotter.id)}
          >
            <span>
              {client ? client.code : '?'} · {blotter.kind === 'batch' ? blotter.subtitle : WINDOWS[blotter.kind].tab}
            </span>
            <button
              type="button"
              className="doctab__close"
              aria-label={`Close ${blotter.title}`}
              onClick={(e) => {
                e.stopPropagation();
                closeBlotter(blotter.id);
              }}
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}

export function StatusBar() {
  const { status, busy, blotters, clientsError } = useWorkspace();
  const tone = clientsError ? 'error' : busy ? 'busy' : 'ok';
  return (
    <div className="statusbar">
      <span>
        <span className={`statusbar__dot statusbar__dot--${tone}`} />
        {clientsError ? 'Backend unreachable' : status}
      </span>
      <span className="statusbar__spacer" />
      <span>{blotters.length} window{blotters.length === 1 ? '' : 's'} open</span>
      <span>AI Finance Controller · prototype build</span>
    </div>
  );
}
