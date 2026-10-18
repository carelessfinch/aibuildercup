export type RunStatus =
  | "queued"
  | "running"
  | "awaiting_signoff"
  | "signed_off"
  | "escalated"
  | "failed";

export interface RunEvent {
  sequence: number;
  event_type: string;
  actor: string;
  message: string;
  created_at: string;
  data: Record<string, unknown>;
}

export interface RunCreated {
  run_id: string;
  status: RunStatus;
  submitted_at: string;
  events_url: string;
}

