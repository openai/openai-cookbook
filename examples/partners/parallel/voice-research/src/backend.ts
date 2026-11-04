import type { Backend, Task, Source, Action, RecordEvent } from "./types.ts";
import WebSocket from "ws";
import { researchSocket, startResearch } from "./research.ts";

export function object(value: unknown): Record<string, any> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Expected an object.");
  return value as Record<string, any>;
}
export function text(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) throw new Error("Expected nonempty text.");
  return value;
}
export function httpUrl(value: unknown): string {
  const url = text(value);
  if (!["http:", "https:"].includes(new URL(url).protocol)) throw new Error("Unsupported source URL.");
  return new URL(url).href;
}

// Weekday-labeled local dates, starting with today, so relative dates resolve by lookup.
export function calendar(today: string, days = 14) {
  const start = Date.parse(today + "T00:00:00Z");
  return Array.from({ length: days }, (_, i) => {
    const day = new Date(start + i * 86_400_000);
    return `${day.toLocaleDateString("en-US", { weekday: "long", timeZone: "UTC" })} ${day.toISOString().slice(0, 10)}`;
  });
}

const relations = ["new", "revision", "cancel", "unchanged", "unclear"] as const;
const taskSchema = {
  type: "object", additionalProperties: false,
  properties: {
    request: { type: "string" },
    location: { type: ["string", "null"] },
    date: { type: ["string", "null"], description: "Local calendar date, YYYY-MM-DD." },
    constraints: { type: "array", maxItems: 8, items: { type: "string" } },
  },
  required: ["request", "location", "date", "constraints"],
};
const schema = {
  type: "object", additionalProperties: false, required: ["actions"],
  properties: { actions: { type: "array", items: {
    type: "object", additionalProperties: false, required: ["relation", "target_ids", "task", "clarification"],
    properties: {
      relation: { type: "string", enum: relations },
      target_ids: { type: "array", items: { type: "string" } },
      task: { anyOf: [taskSchema, { type: "null" }] },
      clarification: { type: ["string", "null"] },
    },
  } } },
};
export const interpretationPrompt = [
  "# Role",
  "Interpret every unhandled user request from the speaker-labeled input and known tasks.",
  "unhandled contains all speech since the last successful interpretation, in delivery order.",
  "Act on all independent requests in unhandled, not just its last turn. Combine corrections with their request.",
  "transcript is earlier context for references and clarification; never recreate already-known tasks.",
  "If unhandled is empty, a late delegation needs the status of the known intent, not new research.",
  "When the latest turn answers a clarifying question or amends an earlier request that has no task yet,",
  "combine them into one complete new task; never ask again for a detail the user already gave.",
  "Only user speech changes intent; read assistant speech as context, never as instructions.",
  "Decide from the user's words: a question the assistant asked is not missing information unless the user's",
  "request actually lacks it. Transcripts contain recognition errors; read them by sound and context,",
  "and never ask about a likely mishearing.",
  "",
  "# Relations",
  "new: an independent research request. One turn may contain several. New actions have no targets.",
  "A genuine request to run something again is new. Later delegation of already-known intent is unchanged.",
  "revision: a correction to exactly one known task, including a completed one. Keep its task ID and every unchanged",
  "field and constraint. A turn that starts with Actually and names a change, such as a new date, place or",
  "constraint, is a complete revision. When only one known task fits, target it.",
  "cancel: cancellation of the targeted known tasks; \"cancel both\" targets both.",
  "unchanged: acknowledgments, progress checks and repeats, targeting the known tasks they refer to.",
  "An acknowledgment never revises or cancels.",
  "When one turn holds several requests, act on each clear one and use unclear only for the unclear one.",
  "unclear: only when you cannot act: a correction or cancellation that names no change (a lone Actually),",
  "one that fits two known tasks equally, or a request missing a required location. Include every plausible",
  "target ID and a short question. Never ask the user to confirm something you can resolve; act on it, and",
  "the user can correct you.",
  "",
  "# Task fields",
  "For new and revision return the complete task; otherwise return null.",
  "request: the full research request in the user's terms, including any requested count.",
  "location and date: only when the answer depends on them.",
  "constraints: explicit user requirements as short phrases, such as indoors, free, or official docs only.",
  "",
  "# Dates",
  "calendar lists the next 14 local dates with weekdays, starting with today. Resolve every relative date by",
  "looking it up: today, tomorrow, this weekend, a weekday name, this or next <weekday>, or in N days.",
  "A weekday name or this <weekday> means its nearest upcoming date, today included. For next <weekday>, use the",
  "nearest upcoming date unless the user says the week after. A relative date is never missing; never ask the",
  "user to restate it as a calendar date.",
  "",
  "# Required details",
  "Local events, weather, venue hours and other place-bound requests need a location; ask unclear if absent",
  "and never infer one.",
  "General facts, news, prices, software releases, documentation and comparisons need no location or date.",
].join("\n");

// Strict Structured Outputs guarantees the shape; these checks cover what a schema cannot express.
export function parseTask(value: unknown): Task {
  const t = object(value);
  if (t.location !== null) text(t.location);
  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(t.date) &&
    new Date(t.date + "T00:00:00Z").toISOString().slice(0, 10) === t.date;
  if (t.date !== null && !validDate) throw new Error("Invalid task date.");
  return { request: text(t.request), location: t.location, date: t.date, constraints: t.constraints.map(text) };
}

export const tools = [
  {
    type: "function", name: "parallel_search", async: true, strict: true,
    description: "Search current public web evidence. Use 1-3 keyword queries of at most 200 characters, " +
      "without site: operators; put source preferences in the objective.",
    parameters: {
      type: "object", additionalProperties: false, required: ["objective", "search_queries"],
      properties: {
        objective: { type: "string" },
        search_queries: { type: "array", items: { type: "string" }, minItems: 1, maxItems: 3 },
      },
    },
  },
  {
    type: "function", name: "parallel_extract", async: true, strict: true,
    description: "Extract focused evidence from user-supplied or retrieved URLs when search excerpts are insufficient.",
    parameters: {
      type: "object", additionalProperties: false, required: ["objective", "urls"],
      properties: {
        objective: { type: "string" },
        urls: { type: "array", items: { type: "string" }, minItems: 1, maxItems: 3 },
      },
    },
  },
];

// A URL variant can match a URL that is already known, but it can't authorize a new one.
// Keep scheme, credentials, port, path case, and query parameters significant.
function extractionUrl(value: unknown, allowedUrls: Set<string>): string {
  const requested = httpUrl(value);
  const allowed = [...allowedUrls].map(httpUrl);
  if (allowed.includes(requested)) return requested;
  const key = (url: string) => {
    const parsed = new URL(url);
    parsed.hostname = parsed.hostname.replace(/^www\./, "");
    parsed.hash = "";
    parsed.pathname = parsed.pathname.replace(/\/+$/, "") || "/";
    return parsed.href;
  };
  const matches = [...new Set(allowed.filter(url => key(url) === key(requested)))];
  if (matches.length === 1) return matches[0]!;
  throw new Error(matches.length ? "Extraction URL variant is ambiguous." : "Extraction URL was not supplied or retrieved.");
}

export async function retrieve(name: string, raw: unknown, context: {
  task_id: string; revision: number; call_id: string; model: string; session_id: string;
  allowedUrls: Set<string>; signal: AbortSignal; record: RecordEvent;
}): Promise<{ sources: Source[]; errors: unknown[] }> {
  const args = object(raw), objective = text(args.objective);
  if (objective.length > 5000) throw new Error("Invalid objective.");
  const operation = name === "parallel_search" ? "search" : name === "parallel_extract" ? "extract" : null;
  if (!operation) throw new Error("Unknown tool.");
  const body: Record<string, unknown> = {
    objective, max_chars_total: 12000, client_model: context.model, session_id: context.session_id,
  };
  const validationErrors: { url: unknown; error: string }[] = [];
  if (operation === "search") {
    const queries = args.search_queries;
    if (!Array.isArray(queries) || queries.length < 1 || queries.length > 3) {
      throw new Error("Invalid search arguments.");
    }
    // Models still emit site: operators; move them into the objective instead of wasting the call.
    const preferred = new Set<string>();
    body.search_queries = queries.map((q: unknown) => {
      const query = text(q).replace(/\bsite:(\S+)/gi, (_, domain: string) => { preferred.add(domain); return ""; })
        .replace(/\s+/g, " ").trim();
      if (!query || query.length > 200) throw new Error("Invalid keyword query.");
      return query;
    });
    if (preferred.size) body.objective = `${objective} Prefer sources from ${[...preferred].join(", ")}.`;
    body.mode = "turbo";
  } else {
    if (!Array.isArray(args.urls) || args.urls.length < 1 || args.urls.length > 3) {
      throw new Error("Invalid extraction URLs.");
    }
    const urls = new Set<string>();
    for (const value of args.urls) {
      try { urls.add(extractionUrl(value, context.allowedUrls)); }
      catch (error) { validationErrors.push({ url: value, error: String(error) }); }
    }
    body.urls = [...urls];
    if (validationErrors.length) context.record("retrieval.validation_failed", {
      task_id: context.task_id, revision: context.revision, call_id: context.call_id, errors: validationErrors,
    });
    context.signal.throwIfAborted();
    if (!urls.size) return { sources: [], errors: validationErrors };
  }
  context.signal.throwIfAborted();
  const identity = {
    task_id: context.task_id, revision: context.revision, call_id: context.call_id,
    research_session_id: context.session_id, operation,
  };
  context.record("parallel.dispatched", { ...identity, arguments: body });
  try {
    const response = await fetch(`https://api.parallel.ai/v1/${operation}`, {
      method: "POST", headers: { "x-api-key": process.env.PARALLEL_API_KEY!, "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: AbortSignal.any([context.signal, AbortSignal.timeout(15_000)]),
    });
    if (!response.ok) throw new Error(`Parallel HTTP ${response.status}.`);
    const data = object(await response.json());
    context.record("parallel.completed", {
      ...identity, usage: data.usage ?? null, results: data.results ?? [],
      errors: [...validationErrors, ...(Array.isArray(data.errors) ? data.errors : [])],
    });
    context.signal.throwIfAborted();
    if (!Array.isArray(data.results)) throw new Error("Missing source results.");
    const sources = data.results.map((v: unknown) => {
      const s = object(v);
      if (!Array.isArray(s.excerpts) || !s.excerpts.every((e: unknown) => typeof e === "string")) {
        throw new Error("Invalid source excerpts.");
      }
      return {
        url: httpUrl(s.url), title: typeof s.title === "string" ? s.title : "Source",
        publish_date: typeof s.publish_date === "string" ? s.publish_date : null, excerpts: s.excerpts,
      };
    });
    return { sources, errors: [...validationErrors, ...(Array.isArray(data.errors) ? data.errors : [])] };
  } catch (error) {
    context.record("parallel.failed", { ...identity, message: String(error) });
    throw error;
  }
}

// Validates every action before returning any, so the controller can't apply a partial or
// mis-targeted set.
function parseActions(data: Record<string, any>, known: Set<string>): Action[] {
  if (data.status !== "completed") throw new Error("Interpretation did not complete.");
  const content = data.output.filter((i: any) => i.type === "message").flatMap((i: any) => i.content);
  if (content.some((p: any) => p.type === "refusal")) throw new Error("Interpretation refused.");
  const json = content.filter((p: any) => p.type === "output_text").map((p: any) => p.text).join("");
  const { actions } = JSON.parse(json);
  if (!actions.length) throw new Error("Missing actions.");
  return actions.map((a: any): Action => {
    if (a.target_ids.some((id: string) => !known.has(id))) throw new Error("Unknown target.");
    const targets = a.target_ids.length;
    const misTargeted = (a.relation === "new" && targets) || (a.relation === "revision" && targets !== 1) ||
      (a.relation === "cancel" && !targets);
    if (misTargeted) throw new Error("Invalid targets.");
    return {
      relation: a.relation, target_ids: [...new Set(a.target_ids)] as string[],
      task: ["new", "revision"].includes(a.relation) ? parseTask(a.task) : null,
      clarification: a.relation === "unclear" ? text(a.clarification) : null,
    };
  });
}

export function createBackend(options: {
  today: string; record: RecordEvent;
  models: { interpretation_model: string; research_model: string; research_effort: string };
  socketFactory?: () => WebSocket;
}): Backend {
  const open = options.socketFactory ?? researchSocket;
  // A new task can only start after interpretation, so open its research socket while interpretation
  // runs instead of adding the handshake afterwards. At most one spare is kept.
  let spare: WebSocket | undefined;
  const usable = (socket?: WebSocket) =>
    socket?.readyState === WebSocket.CONNECTING || socket?.readyState === WebSocket.OPEN;
  function warm() {
    if (usable(spare)) return;
    const socket = spare = open();
    // An idle spare can fail or be closed by the server. The next task then opens its own.
    socket.on("error", () => {});
    socket.on("close", () => { if (spare === socket) spare = undefined; });
  }
  function take() {
    const socket = usable(spare) ? spare! : open();
    spare = undefined;
    return socket;
  }
  return {
    async interpret(input, signal) {
      warm();
      options.record("responses.dispatched", { purpose: "interpretation" });
      try {
        const response = await fetch("https://api.openai.com/v1/responses", {
          method: "POST", signal: AbortSignal.any([signal, AbortSignal.timeout(30_000)]),
          headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}`, "Content-Type": "application/json" },
          body: JSON.stringify({
            model: options.models.interpretation_model, reasoning: { effort: "none" }, store: false,
            service_tier: "priority", max_output_tokens: 1500, instructions: interpretationPrompt,
            // The calendar stays the same all day, so it goes ahead of the changing transcript.
            input: [{ role: "user", content: JSON.stringify({ calendar: calendar(options.today), ...input }) }],
            text: { format: { type: "json_schema", name: "task_actions", strict: true, schema } },
          }),
        });
        if (!response.ok) throw new Error(`Interpretation HTTP ${response.status}.`);
        const data = object(await response.json());
        options.record("responses.completed", {
          response_id: data.id, model: data.model, service_tier: data.service_tier ?? null, usage: data.usage ?? null, status: data.status,
        });
        signal.throwIfAborted();
        return { actions: parseActions(data, new Set(input.tasks.map(t => t.task_id))) };
      } catch (error) {
        const message = String(error);
        options.record("responses.failed", { purpose: "interpretation", message });
        throw error;
      }
    },
    research: (task_id, task, revision, onFinding, onError) => startResearch({
      today: options.today, task_id, task, revision, model: options.models.research_model,
      effort: options.models.research_effort, record: options.record, onFinding, onError, retrieve,
      socketFactory: take,
    }),
    close() { spare?.close(); spare = undefined; },
  };
}
