import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { api } from '../api/client';
import type { Client } from '../types';

export type BlotterKind =
  | 'recon'
  | 'batch'
  | 'sources'
  | 'tax'
  | 'matching'
  | 'forecast'
  | 'exceptions';

/**
 * A command the open window contributes to the ribbon.
 *
 * The ribbon used to render the same three groups on every tab with only the
 * picture changing, which is decoration, not a toolbar. Windows now publish
 * what they can actually do and the ribbon renders that, so the commands under
 * a tab are the commands that tab performs.
 */
export interface RibbonCommand {
  id: string;
  label: string;
  group: string;
  run: () => void;
  disabled?: boolean;
  primary?: boolean;
  title?: string;
}

export interface Blotter {
  /** Stable identity: opening the same window for the same client/batch focuses
   *  the existing tab instead of stacking duplicates. */
  id: string;
  kind: BlotterKind;
  clientId: string;
  title: string;
  subtitle?: string;
  batchId?: string;
}

interface WorkspaceValue {
  clients: Client[];
  clientsError: string | null;
  loadingClients: boolean;
  reloadClients: () => void;
  clientById: (id: string) => Client | undefined;

  blotters: Blotter[];
  activeId: string | null;
  activeBlotter: Blotter | null;
  openBlotter: (spec: Omit<Blotter, 'id'>) => void;
  closeBlotter: (id: string) => void;
  focusBlotter: (id: string) => void;
  closeAll: () => void;

  /** Bumped whenever something should re-read the server: a run started, a
   *  config was saved, the agent acted. Blotters watch it instead of each
   *  inventing its own refresh plumbing. */
  revision: number;
  refresh: () => void;

  status: string;
  setStatus: (message: string) => void;
  busy: boolean;
  setBusy: (busy: boolean) => void;

  commands: RibbonCommand[];
  publishCommands: (blotterId: string, commands: RibbonCommand[]) => void;
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

function blotterId(spec: Omit<Blotter, 'id'>): string {
  return [spec.kind, spec.clientId, spec.batchId ?? ''].join('|');
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [clients, setClients] = useState<Client[]>([]);
  const [clientsError, setClientsError] = useState<string | null>(null);
  const [loadingClients, setLoadingClients] = useState(true);

  const [blotters, setBlotters] = useState<Blotter[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [status, setStatus] = useState('Ready');
  const [busy, setBusy] = useState(false);
  const [commandsByBlotter, setCommandsByBlotter] = useState<Record<string, RibbonCommand[]>>({});

  const publishCommands = useCallback((blotterId: string, next: RibbonCommand[]) => {
    setCommandsByBlotter((current) => ({ ...current, [blotterId]: next }));
  }, []);

  const loadClients = useCallback(() => {
    setLoadingClients(true);
    api
      .clients()
      .then((rows) => {
        setClients(rows);
        setClientsError(null);
      })
      .catch((error: Error) => setClientsError(error.message))
      .finally(() => setLoadingClients(false));
  }, []);

  useEffect(loadClients, [loadClients]);

  const openBlotter = useCallback((spec: Omit<Blotter, 'id'>) => {
    const id = blotterId(spec);
    setBlotters((current) => {
      const existing = current.findIndex((b) => b.id === id);
      if (existing >= 0) {
        // Re-opening refreshes the title/subtitle (a batch's code can change
        // between runs) without disturbing tab order.
        const next = [...current];
        next[existing] = { ...spec, id };
        return next;
      }
      return [...current, { ...spec, id }];
    });
    setActiveId(id);
  }, []);

  const closeBlotter = useCallback((id: string) => {
    setBlotters((current) => {
      const index = current.findIndex((b) => b.id === id);
      if (index < 0) return current;
      const next = current.filter((b) => b.id !== id);
      setActiveId((active) => {
        if (active !== id) return active;
        const neighbour = next[index] ?? next[index - 1] ?? null;
        return neighbour ? neighbour.id : null;
      });
      return next;
    });
  }, []);

  const value = useMemo<WorkspaceValue>(
    () => ({
      clients,
      clientsError,
      loadingClients,
      reloadClients: loadClients,
      clientById: (id) => clients.find((c) => c.id === id),
      blotters,
      activeId,
      activeBlotter: blotters.find((b) => b.id === activeId) ?? null,
      openBlotter,
      closeBlotter,
      focusBlotter: setActiveId,
      closeAll: () => {
        setBlotters([]);
        setActiveId(null);
      },
      revision,
      refresh: () => setRevision((r) => r + 1),
      status,
      setStatus,
      busy,
      setBusy,
      commands: activeId ? (commandsByBlotter[activeId] ?? []) : [],
      publishCommands,
    }),
    [clients, clientsError, loadingClients, loadClients, blotters, activeId, openBlotter, closeBlotter,
     revision, status, busy, commandsByBlotter, publishCommands],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceValue {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error('useWorkspace must be used inside a WorkspaceProvider');
  return value;
}

/**
 * Loads data for the active blotter and re-loads it when the workspace
 * revision changes (a run finished, a config was saved) or on an interval
 * while something is in flight.
 */
export function useLoader<T>(
  loader: () => Promise<T>,
  deps: unknown[],
  options: { pollMs?: number } = {},
): { data: T | null; error: string | null; loading: boolean; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loaderRef.current()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const { pollMs } = options;
  useEffect(() => {
    if (!pollMs) return;
    const handle = window.setInterval(() => setTick((t) => t + 1), pollMs);
    return () => window.clearInterval(handle);
  }, [pollMs]);

  return { data, error, loading, reload: () => setTick((t) => t + 1) };
}


/**
 * Publishes the open window's commands to the ribbon for as long as it is
 * mounted. Commands are re-published whenever their closure changes, so a
 * button that depends on the current selection stays correct.
 */
export function useRibbonCommands(blotterId: string, commands: RibbonCommand[]): void {
  const { publishCommands } = useWorkspace();
  const signature = commands
    .map((c) => `${c.id}:${c.label}:${c.disabled ? 1 : 0}`)
    .join('|');

  useEffect(() => {
    publishCommands(blotterId, commands);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blotterId, signature]);
}
