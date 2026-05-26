export type FieldState = {
  field_id: string;
  section: "A" | "B" | "C" | "D" | "E";
  label: string;
  value: string | number | boolean | null;
  unit?: string | null;
  status: string;
  confidence: string;
  source?: Record<string, unknown> | null;
  evidence_ids: string[];
  candidates: Array<Record<string, unknown>>;
  note?: string | null;
};

export type InteractionOption = {
  value: unknown;
  label?: string | null;
  suitability?: string | null;
  risk_note?: string | null;
  recommended?: boolean;
  evidence_ids?: string[];
  field_updates?: Record<string, unknown>;
};

export type InteractionQuestion = {
  question_id: string;
  field_ids: string[];
  prompt: string;
  input_kind: string;
  required: boolean;
  options: InteractionOption[];
  missing_reason?: string | null;
  ambiguity_note?: string | null;
};

export type InteractionRequest = {
  request_id: string;
  interaction_mode: string;
  purpose: string;
  title: string;
  summary: string;
  assistant_message?: string;
  questions: InteractionQuestion[];
};

export type RunSnapshot = {
  run_id: string;
  mode: string;
  interaction_mode?: string;
  status: string;
  pending_interaction?: InteractionRequest | null;
  interaction_requests: InteractionRequest[];
  fields: Record<string, FieldState>;
  trace: Array<Record<string, unknown>>;
  confirmations: Array<Record<string, unknown>>;
  field_report: Record<string, unknown>;
  quality_report?: Record<string, unknown> | null;
  draft_markdown: string;
  has_draft: boolean;
  output_dir: string;
};
