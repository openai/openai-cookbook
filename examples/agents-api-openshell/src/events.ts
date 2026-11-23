import type { AgentSessionEvent } from "openai/resources/beta/agents/agents";

export function redact(text: string, secrets: readonly string[]) {
  let clean = text;
  for (const secret of [...secrets].sort((a, b) => b.length - a.length)) {
    if (secret) clean = clean.replaceAll(secret, "[redacted]");
  }
  // Also cover keys encountered in agent output that were never passed to this client.
  return clean.replace(/sk-[A-Za-z0-9_-]{12,}/gu, "[redacted]")
    .replace(/[\x00-\x08\x0b-\x1f\x7f-\x9f]/gu, "");
}

export class TextOutput {
  readonly #parts = new Map<string, string>();

  constructor(
    private readonly safe: (text: string) => string,
    private readonly write: (text: string) => void,
  ) {}

  delta(part: string, text: string) {
    const pending = (this.#parts.get(part) ?? "") + text;
    // A credential can straddle deltas. Retain the final whitespace-delimited token.
    const end = pending.search(/\S*$/u);
    this.#parts.set(part, pending.slice(end));
    if (end > 0) this.write(this.safe(pending.slice(0, end)));
  }

  done(part: string, fallback: string) {
    this.write(this.safe(this.#parts.get(part) ?? fallback));
    this.#parts.delete(part);
  }

  flush() {
    for (const part of this.#parts.keys()) this.done(part, "");
  }
}

export type TurnOutcome = "completed" | "cancelled" | "failed";
export type EventUpdate =
  | { kind: "connected" | "disconnected" | "idle" | "turn-started" }
  | { kind: "fatal"; message: string }
  | { kind: "turn"; outcome: TurnOutcome }
  | { kind: "text"; phase: "delta" | "done"; part: string; text: string }
  | { kind: "command"; command: string; phase: "started" | "finished"; exitCode: number | null };

export function reduceEvent(event: AgentSessionEvent): EventUpdate | undefined {
  switch (event.type) {
    case "agent.session.environment.connected":
      return { kind: "connected" };
    case "agent.session.environment.disconnected":
      return { kind: "disconnected" };
    case "agent.session.environment.failed":
      return { kind: "fatal", message: "Executor registration failed." };
    case "agent.session.environment.expired":
      return { kind: "fatal", message: "The executor environment expired." };
    case "agent.session.failed":
      return { kind: "fatal", message: "The Agents API marked the session failed." };
    case "error":
      return { kind: "fatal", message: "The Agents API stream reported an error." };
    case "agent.session.idle":
      return { kind: "idle" };
    case "agent.session.turn.created":
      if (event.turn.subagent_id == null) return { kind: "turn-started" };
      return;
    case "agent.session.turn.completed":
    case "agent.session.turn.cancelled":
    case "agent.session.turn.failed":
      if (event.turn.subagent_id != null) return;
      return {
        kind: "turn",
        outcome: event.type === "agent.session.turn.completed" ? "completed"
          : event.type === "agent.session.turn.cancelled" ? "cancelled" : "failed",
      };
    case "agent.session.turn.output_text.delta":
    case "agent.session.turn.output_text.done":
      return {
        kind: "text",
        part: `${event.item_id}:${event.content_index}`,
        phase: event.type === "agent.session.turn.output_text.delta" ? "delta" : "done",
        text: event.type === "agent.session.turn.output_text.delta" ? event.delta : event.text,
      };
    case "agent.session.turn.item.added":
    case "agent.session.turn.item.done":
      if (event.item.type !== "command_execution") return;
      return {
        kind: "command",
        command: event.item.command,
        phase: event.type === "agent.session.turn.item.added" ? "started" : "finished",
        exitCode: event.item.exit_code,
      };
  }
}
