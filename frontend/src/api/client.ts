import type {
  AgentResponse,
  BankAccount,
  BatchDefinition,
  BatchLogEntry,
  BatchReport,
  CashForecast,
  CashPosition,
  ChatTurn,
  Client,
  ConfigSectionResponse,
  DataSource,
  ImportProbeResult,
  ImportSource,
  MatchingConfigView,
  ReconciliationType,
  RunAccepted,
  TaxConfigView,
} from '../types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(
      `Cannot reach the API at ${BASE_URL}. Is the backend running on port 8000?`,
      0,
    );
  }

  if (!response.ok) {
    // FastAPI reports validation and domain failures in `detail`; surfacing
    // that verbatim is what lets a rejected edit explain itself in the dialog
    // instead of collapsing to "save failed".
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') detail = body.detail;
      else if (body?.detail) detail = JSON.stringify(body.detail);
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body ?? {}) });
const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
const put = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'PUT', body: JSON.stringify(body) });

export const api = {
  clients: () => request<Client[]>('/clients'),
  dataSources: (clientId: string) => request<DataSource[]>(`/clients/${clientId}/data-sources`),
  bankAccounts: (clientId: string) => request<BankAccount[]>(`/clients/${clientId}/bank-accounts`),
  updateBankAccount: (accountId: string, body: Record<string, unknown>) =>
    patch<BankAccount>(`/bank-accounts/${accountId}`, body),
  reconciliationTypes: () => request<ReconciliationType[]>('/reconciliation-types'),

  // -- Reconciliation Management ------------------------------------------
  batchDefinitions: (clientId: string) =>
    request<BatchDefinition[]>(`/clients/${clientId}/batch-definitions`),
  updateBatchDefinition: (definitionId: string, body: Record<string, unknown>) =>
    patch<BatchDefinition>(`/batch-definitions/${definitionId}`, body),
  runBatchDefinition: (definitionId: string) =>
    post<RunAccepted>(`/batch-definitions/${definitionId}/run`, { actor: 'operator' }),
  runBatchDefinitions: (clientId: string, ids?: string[]) =>
    post<RunAccepted>(`/clients/${clientId}/batch-definitions/run`, {
      actor: 'operator',
      batch_definition_ids: ids ?? null,
    }),

  importSources: (clientId: string) => request<ImportSource[]>(`/clients/${clientId}/import-sources`),
  updateImportSource: (importSourceId: string, body: Record<string, unknown>) =>
    patch<ImportSource>(`/import-sources/${importSourceId}`, body),
  probeImportSource: (importSourceId: string) =>
    post<ImportProbeResult>(`/import-sources/${importSourceId}/probe`),

  // -- Batch runs ----------------------------------------------------------
  batchReport: (batchId: string) => request<BatchReport>(`/batches/${batchId}/report`),
  batchLogs: (batchId: string, sinceSeq = 0) =>
    request<BatchLogEntry[]>(`/batches/${batchId}/logs?since_seq=${sinceSeq}`),

  // -- Configuration windows ----------------------------------------------
  taxConfig: (clientId: string) =>
    request<ConfigSectionResponse<TaxConfigView>>(`/clients/${clientId}/tax-config`),
  saveTaxConfig: (clientId: string, sections: Record<string, unknown>) =>
    put<ConfigSectionResponse<TaxConfigView>>(`/clients/${clientId}/tax-config`, {
      sections,
      actor: 'operator',
    }),
  matchingConfig: (clientId: string) =>
    request<ConfigSectionResponse<MatchingConfigView>>(`/clients/${clientId}/matching-config`),
  saveMatchingConfig: (clientId: string, sections: Record<string, unknown>) =>
    put<ConfigSectionResponse<MatchingConfigView>>(`/clients/${clientId}/matching-config`, {
      sections,
      actor: 'operator',
    }),

  // -- Cash ----------------------------------------------------------------
  cashPosition: (clientId: string) => request<CashPosition>(`/clients/${clientId}/cash-position`),
  cashForecast: (clientId: string) => request<CashForecast>(`/clients/${clientId}/cash-forecast`),

  // -- Agent ---------------------------------------------------------------
  chat: (messages: ChatTurn[], clientId: string | null) =>
    post<AgentResponse>('/agent/chat', {
      messages: messages.map((m) => ({ role: m.role, content: m.content })),
      client_id: clientId,
    }),
};
