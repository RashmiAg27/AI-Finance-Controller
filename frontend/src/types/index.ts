export interface Client {
  id: string;
  code: string;
  name: string;
  status: string;
  /** IANA zone name (e.g. "Asia/Kolkata") this client's timestamps should be
   *  displayed in. Every stored timestamp is UTC regardless -- this only
   *  controls rendering, never what's persisted or a business date. */
  display_timezone: string;
}

export interface DataSource {
  source_id: string;
  name: string;
  role: 'INTERNAL' | 'EXTERNAL';
  file_format: string;
  is_required: boolean;
}

export interface BankAccount {
  id: string;
  client_id: string;
  account_code: string;
  display_name: string;
  bank_name: string;
  account_number_masked: string;
  ifsc: string | null;
  branch: string | null;
  account_type: string;
  purpose: string;
  currency: string;
  gl_code: string | null;
  is_active: boolean;
}

export interface ReconciliationType {
  code: string;
  label: string;
  left_side?: string;
  right_side?: string;
  natural_key?: string;
  legitimate_differences?: string;
  scoped_to_account?: boolean;
  known: boolean;
}

export type ImportSourceKind =
  | 'LOCAL_DIRECTORY'
  | 'EMAIL_INBOX'
  | 'SFTP_CONNECTION'
  | 'API_CONNECTION';

export interface ImportSource {
  id: string;
  client_id: string;
  code: string;
  name: string;
  kind: ImportSourceKind;
  connection_json: Record<string, unknown>;
  enabled: boolean;
  location: string | null;
  last_polled_at: string | null;
  last_status: string | null;
  last_message: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface ImportProbeResult {
  kind: string;
  location: string;
  status: string;
  files: { source_id: string; filename: string; size_bytes: number }[];
  log: string[];
}

export interface BatchRunSummary {
  id: string;
  batch_code: string;
  status: string;
  current_stage: string | null;
  progress_pct: number;
  business_date: string | null;
  triggered_by_type: string | null;
  triggered_by: string | null;
  created_at: string | null;
  closed_at: string | null;
  failure_reason: string | null;
}

export type BatchDefinitionState =
  | 'DISABLED'
  | 'AWAITING_DATA'
  | 'DATA_AVAILABLE'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED';

export interface BatchDefinition {
  id: string;
  client_id: string;
  code: string;
  name: string;
  description: string | null;
  batch_type: string;
  reconciliation_type: string;
  reconciliation_label: string | null;
  bank_account_id: string | null;
  bank_account_label: string | null;
  trigger_type: string;
  trigger_detail: string | null;
  import_source_id: string | null;
  import_source_code: string | null;
  import_source_kind: string | null;
  import_location: string | null;
  source_ids: string[];
  enabled: boolean;
  cutoff_time: string | null;
  sla_minutes: number;
  owner_team: string | null;
  updated_at: string | null;
  updated_by: string | null;
  state: BatchDefinitionState;
  data_available: boolean | null;
  available_source_ids: string[];
  missing_source_ids: string[];
  latest_run: BatchRunSummary | null;
}

export interface RunAccepted {
  queued: BatchRunSummary[];
  skipped: { batch_definition_id: string; code: string; reason: string }[];
}

export interface BatchLogEntry {
  seq: number;
  created_at: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'EXCEPTION';
  stage: string;
  message: string;
  detail_json: Record<string, unknown>;
}

export interface ExceptionItem {
  id: string;
  exception_type: string;
  severity: string;
  status: string;
  amount_impact: string | null;
  likely_cause: string | null;
  confidence: number | null;
  recommended_action: string | null;
  transactions: {
    transaction_id: string;
    source_id: string;
    reference: string | null;
    amount: string;
    currency: string | null;
    counterparty: string | null;
    transaction_date: string;
    description: string | null;
  }[];
}

/** What the configured fee/tax rules were asked, and what they answered --
 *  recorded whether or not they explained the gap. */
export interface FeeRuleEvaluation {
  explained: boolean;
  reason:
    | 'NO_RULES_CONFIGURED'
    | 'NET_EXCEEDS_GROSS'
    | 'RULES_PRODUCE_A_DIFFERENT_NET'
    | 'EXPLAINED_BY_CONFIGURED_RULES';
  narrative: string;
  difference: string;
  applicable_when?: { internal_instrument_type: string; external_instrument_type: string };
  attempted_lines?: {
    label: string;
    amount: string;
    verification_status?: string;
    source_reference?: string | null;
  }[];
  total_deductions_if_applied?: string;
  net_if_rules_applied?: string;
  observed_net?: string;
  residual?: string;
  rounding_tolerance?: string;
}

export interface SettlementDetail {
  id: string;
  gross_amount: string;
  net_amount_expected: string;
  net_amount_observed: string;
  is_fully_explained: boolean;
  match_type: string | null;
  fee_rule_evaluation: FeeRuleEvaluation | null;
  components: { type: string; amount: string; description: string | null }[];
}

export interface BatchReport {
  batch: {
    id: string;
    batch_code: string;
    client_id: string;
    status: string;
    current_stage: string | null;
    progress_pct: number;
    business_date: string | null;
    triggered_by: string | null;
    triggered_by_type: string | null;
    created_at: string | null;
    closed_at: string | null;
    failure_reason: string | null;
    batch_definition_id: string | null;
    batch_definition_code: string | null;
    batch_definition_name: string | null;
  };
  files: { filename: string; file_format: string; size_bytes: number; checksum_sha256: string }[];
  transactions: { total: number; by_source: Record<string, number> };
  reconciliation: {
    run_id: string | null;
    run_status: string | null;
    stats: Record<string, unknown>;
    match_count: number;
    matches_by_type: Record<string, number>;
    matches_by_cardinality: Record<string, number>;
    matched_transaction_count: number;
    match_rate_pct: number | null;
  };
  exceptions: {
    total: number;
    open: number;
    by_type: Record<string, number>;
    by_severity: Record<string, number>;
    total_amount_at_risk: string;
    items: ExceptionItem[];
  };
  settlements: {
    total: number;
    unexplained: number;
    components: SettlementDetail[];
  };
  cash: {
    as_of: string | null;
    confirmed_cash: string | null;
    pending_cash: string | null;
    expected_inflows: string | null;
    expected_outflows: string | null;
    unreconciled_amount: string | null;
    forecast: {
      horizon_days: number;
      as_of: string;
      expected_value: string;
      low_estimate: string;
      high_estimate: string;
      drivers: Record<string, unknown> | null;
      assumptions_note: string | null;
    } | null;
  };
  log?: BatchLogEntry[];
}

// ---------------------------------------------------------------------------
// Configuration windows
// ---------------------------------------------------------------------------

export interface StatutoryCharge {
  code: string;
  label: string;
  basis: 'GROSS' | 'FEE' | 'FEE_PLUS_TAX';
  rate_percent: number;
  flat_amount: number;
  applies_to_instrument_types: string[];
  enabled: boolean;
  source_authority: string | null;
  source_reference: string | null;
  verification_status: string;
  note: string | null;
}

export interface TaxFeeRules {
  applicable_when: { internal_instrument_type: string; external_instrument_type: string };
  fee: { rate_percent: number; verification_status: string; note: string | null };
  tax_on_fee: { tax_rule_id: string };
  commission: {
    label: string;
    rate_percent: number;
    minimum_amount: number;
    maximum_amount: number | null;
    verification_status: string;
    note: string | null;
  } | null;
  statutory_charges: StatutoryCharge[];
  rounding_tolerance: number;
  date_field: string;
  date_tolerance_days: number;
  confidence: number;
}

export interface TaxConfigView {
  client_id: string;
  config_version: number;
  configured: boolean;
  tax_fee_rules: TaxFeeRules | null;
}

export interface FieldMapping {
  source_field: string;
  canonical_field: string;
  identifier_type: string | null;
  data_type: string;
  date_format: string | null;
  sign_convention: string | null;
  value_map: Record<string, string> | null;
  required: boolean;
}

export interface DataSourceConfig {
  source_id: string;
  role: string;
  file_format: string;
  sheet_name: string | null;
  is_required: boolean;
  field_mappings: FieldMapping[];
  identifier_priority: string[];
  static_fields: Record<string, string>;
}

export interface MatchingRule {
  rule_id: string;
  pass: number;
  version: number;
  match_on: { left_identifier: string; right_identifier: string; comparison: string }[];
  conditions: Record<string, unknown> | null;
  confidence: number;
}

export interface IdentifierLinkage {
  rule_id: string;
  source_identifier_type: string;
  target_identifier_type: string;
  linkage_type: string;
  transform: string;
  confidence: number;
  rationale: string;
}

export interface MatchingConfigView {
  client_id: string;
  config_version: number;
  data_sources: DataSourceConfig[];
  identifier_linkage: IdentifierLinkage[];
  matching_rules: MatchingRule[];
  normalization_rules: Record<string, unknown>;
  tolerance_defaults: Record<string, unknown>;
  aggregation_rules: Record<string, unknown> | null;
  canonical_fields: string[];
}

export interface ConfigSectionResponse<T> {
  client_id: string;
  config_version: number;
  data: T;
}

export interface CashPosition {
  as_of: string;
  confirmed_cash: string;
  pending_cash: string;
  expected_inflows: string;
  expected_outflows: string;
  unreconciled_amount: string;
  detail: {
    by_bank_account?: Record<string, string>;
    internal_transfer_volume?: string;
    internal_transfer_note?: string;
    [key: string]: unknown;
  };
}

export interface CashForecast {
  horizon_days: number;
  as_of: string;
  expected_value: string;
  low_estimate: string;
  high_estimate: string;
  drivers: Record<string, unknown> | null;
  assumptions_note: string | null;
}

// ---------------------------------------------------------------------------
// Agent
// ---------------------------------------------------------------------------

export interface AgentToolCall {
  tool: string;
  input: Record<string, unknown>;
  result: Record<string, unknown>;
}

export interface AgentResponse {
  text: string;
  tool_calls: AgentToolCall[];
  configured: boolean;
  ui_hint: { open?: string; client_id?: string; batch_id?: string } | null;
  awaiting_confirmation: { action: string; plan: Record<string, unknown>[] } | null;
  tools_available: string[];
}

export interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: AgentToolCall[];
  awaiting?: { action: string; plan: Record<string, unknown>[] } | null;
  error?: boolean;
}
