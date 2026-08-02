export type TaskNoteRequest = {
  callId: string;
  title: string;
  details: string;
};

type RealtimeEvent = Record<string, unknown> & { type: string };

export function parseRealtimeEvent(raw: unknown): RealtimeEvent | null {
  if (typeof raw !== "string") return null;

  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object") return null;
    const event = value as Record<string, unknown>;
    return typeof event.type === "string"
      ? (event as RealtimeEvent)
      : null;
  } catch {
    return null;
  }
}

export function readTaskNoteRequest(
  event: RealtimeEvent,
): TaskNoteRequest | null {
  if (
    event.type !== "response.function_call_arguments.done" ||
    event.name !== "save_task_note" ||
    typeof event.call_id !== "string" ||
    typeof event.arguments !== "string"
  ) {
    return null;
  }

  try {
    const args: unknown = JSON.parse(event.arguments);
    if (!args || typeof args !== "object") return null;

    const { title, details } = args as Record<string, unknown>;
    if (typeof title !== "string" || typeof details !== "string") {
      return null;
    }

    const normalizedTitle = title.trim().slice(0, 120);
    const normalizedDetails = details.trim().slice(0, 1_000);
    if (!normalizedTitle) return null;

    return {
      callId: event.call_id,
      title: normalizedTitle,
      details: normalizedDetails,
    };
  } catch {
    return null;
  }
}
