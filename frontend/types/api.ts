export type JsonRecord = Record<string, unknown>;

export interface SessionTokens {
  access_token: string;
  refresh_token: string;
}

export interface User {
  sub?: string;
  email: string;
  role?: string;
  [key: string]: unknown;
}

export interface AuthResponse extends SessionTokens {
  user?: User;
}

export interface QueryResult extends JsonRecord {
  answer_id?: string;
  query?: string;
  answer?: string;
  abstained?: boolean;
  cers?: {
    percentage?: number;
    score?: number;
    components?: Record<string, number>;
    calibration_status?: string;
    methodology?: string;
    [key: string]: unknown;
  };
  evidence?: Array<JsonRecord>;
  claims?: Array<JsonRecord>;
  conflicts?: unknown[];
  limitations?: unknown[];
  understanding?: JsonRecord;
}

export interface DocumentSummary extends JsonRecord {
  document_id?: string;
  title?: string;
  source?: string;
  status?: string;
  chunk_count?: number;
  ingestion_timestamp?: string;
}

export interface Health extends JsonRecord {
  status?: string;
  runtime?: string;
  evidence_mode?: string;
  capabilities?: JsonRecord;
}

export interface SourceCoverageResponse extends JsonRecord {
  sources?: Array<JsonRecord>;
  refresh_status?: string;
  refresh_finished_at?: string | null;
  refresh_failures?: Array<JsonRecord | string>;
}

export interface DocumentsResponse {
  documents?: DocumentSummary[];
}

export interface GapResponse extends JsonRecord {
  candidate_gaps?: Array<JsonRecord>;
  evidence_document_count?: number;
  limitations?: unknown[];
}

export interface ApiErrorShape {
  detail?: string | JsonRecord;
}

export interface ExperimentInput {
  name: string;
  dataset: string;
  model: string;
  hyperparameters: JsonRecord;
  notes: string;
  status: 'created' | 'running' | 'completed' | 'failed' | 'cancelled';
  workspace_id?: string | null;
}

export interface ExperimentMetric {
  id: string;
  experiment_id: string;
  metric_name: string;
  metric_value: number;
}

export interface ExperimentRecord extends ExperimentInput {
  id: string;
  created_at: string;
  updated_at: string;
  metrics?: ExperimentMetric[];
}
