export type Fragment = { role: "user" | "assistant"; delta: string; start_ms: number; end_ms: number };
export type Utterance = { role: "user" | "assistant"; text: string; start_ms: number; end_ms: number };
// A domain-neutral research request. Location and date are null unless the answer depends on them.
export type Task = { request: string; location: string | null; date: string | null; constraints: string[] };
export type TaskSummary = { task_id: string; revision: number; task: Task; state: string };
export type Action = {
  relation: "new" | "revision" | "cancel" | "unchanged" | "unclear";
  target_ids: string[]; task: Task | null; clarification: string | null;
};
export type Interpretation = { actions: Action[] };
export type Source = { title: string; url: string; publish_date: string | null; excerpts: string[] };
// `sources` are exactly the cited sources. The research run decides `kind`: final once nothing is pending.
export type DisplayAnswer = { display_title?: string; display_items?: { heading: string; detail: string }[] };
export type FindingOutcome = "supported" | "insufficient_evidence";
export type Finding = DisplayAnswer & { outcome: FindingOutcome; spoken_summary: string; sources: Source[]; revision: number; kind: "partial" | "final" };
export type RecordEvent = (type: string, data: Record<string, unknown>) => void;
export type ResearchRun = { update: (task: Task, revision: number) => void; cancel: () => void };
export type Backend = {
  interpret: (input: { transcript: Utterance[]; unhandled?: Utterance[]; tasks: TaskSummary[] }, signal: AbortSignal) => Promise<Interpretation>;
  research: (
    task_id: string, task: Task, revision: number,
    onFinding: (finding: Finding) => void, onError: (revision: number, error: Error) => void,
  ) => ResearchRun;
  // Releases anything held for future tasks, such as an idle research socket.
  close?: () => void;
};

// Which voice updates GPT-Live accepted. Acceptance doesn't mean an update was spoken.
export type VoiceDelivery = {
  id: string; task_id?: string; revision?: number; conclusion?: number;
  purpose: 'finding' | 'cancellation' | 'context'; kind?: 'partial' | 'final';
  type: string; state: 'preparing' | 'submitted' | 'accepted' | 'superseded' | 'failed';
  chunks: { event_id: string; state: 'submitted' | 'accepted' | 'failed' }[];
  updated_at: number;
};
export type VoiceSnapshot = { version: 1; updates: VoiceDelivery[] };
