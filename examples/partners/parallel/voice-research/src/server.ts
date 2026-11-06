import http from "node:http";
import { once } from "node:events";
import { mkdirSync, writeFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { WebSocket } from "ws";
import { createUpdatePreparer } from "./live-updates.ts";
import { TaskController } from "./controller.ts";
import { createBackend } from "./backend.ts";
import type { RecordEvent, VoiceSnapshot } from "./types.ts";

const root = fileURLToPath(new URL("../", import.meta.url));
const settings = JSON.parse(await readFile(root + "settings.json", "utf8"));
const apiKey = process.env.OPENAI_API_KEY;
const parallelKey = process.env.PARALLEL_API_KEY;
const port = Number(process.env.PORT ?? 3000);
if (!apiKey || !parallelKey) throw new Error("Set OPENAI_API_KEY and PARALLEL_API_KEY before starting.");

// Conversation style and when to delegate, laid out like the GPT-Live prompting template. Research
// procedures and evidence rules live in the backend prompt (src/research.ts).
const prompt = [
  "You are a calm, friendly voice research assistant.",
  "Speak warmly and naturally, at an unhurried pace. Be clear and direct, not overly cheerful.",
  "If the user is frustrated, acknowledge it briefly and focus on the next helpful step.",
  "",
  "Backchannel policy: Use moderate backchannels. Acknowledge naturally without competing with the main response.",
  "",
  "Interruption policy: Stop speaking when the user interrupts. Listen to what they say.",
  "",
  "Delegation policy:",
  "Backend tools:",
  "- Web research: finds current public information with sources, such as facts and news, software documentation " +
    "and releases, prices, comparisons, local events, and pages at URLs the user gives. It knows today's date " +
    "and resolves relative dates such as this Saturday.",
  "",
  "Delegate to the backend when:",
  "- The request needs current information, documentation, a comparison, local events, or URL research.",
  "- The user answers a question you asked about a research request.",
  "- A correction or cancellation changes research already requested.",
  "",
  "Do not delegate to the backend when:",
  "- The user greets you, acknowledges progress, or asks you to repeat a still-current result.",
  "- You need a brief clarification to understand the request, such as a missing location for local events.",
  "",
  "Delegate before giving an answer that depends on backend work.",
  "Do not guess the result while waiting.",
  "When the backend confirms a task is cancelled, say it is cancelled, not paused. Before confirmation,",
  "acknowledge only the request to cancel; do not claim the task has stopped yet.",
  "Never ask which date the user means; relative dates such as this Saturday are clear.",
  "Keep the backend's uncertainty and source qualifications when you paraphrase.",
].join("\n");

// What the browser needs: startup and close for its lifecycle, captions, and errors.
const browserEvents = ["session.started", "session.closed", "error", "info",
  "session.input_transcript.delta", "session.output_transcript.delta"].map(type => ({ type }));

type Session = {
  id: string; events: object[]; clients: Set<http.ServerResponse>; closed: boolean; voice: () => VoiceSnapshot; close: () => Promise<boolean>;
};
const sessions = new Map<string, Session>();
const origin = `http://localhost:${port}`;
const localOrigins = new Set([origin, `http://127.0.0.1:${port}`].map(value => new URL(value).origin));

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url ?? "/", origin);
    // Check Host as well as Origin so a website cannot rebind its domain to this local server.
    if (!localOrigins.has(`http://${req.headers.host}`) ||
        (req.headers.origin && !localOrigins.has(req.headers.origin))) {
      json(res, 403, { error: "Use the local app origin." }); return;
    }
    if (req.headers["sec-fetch-site"] === "cross-site") {
      json(res, 403, { error: "Use the local app origin." }); return;
    }
    if (req.method === "GET" && ["/", "/app.js", "/style.css"].includes(url.pathname)) {
      const name = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
      const type = name.endsWith("html") ? "text/html" : name.endsWith("js") ? "text/javascript" : "text/css";
      res.writeHead(200, { "Content-Type": type });
      res.end(await readFile(root + "public/" + name)); return;
    }
    if (req.method === "POST" && url.pathname === "/api/session") { await createSession(req, res); return; }
    const session = sessions.get(url.searchParams.get("id") ?? "");
    if (req.method === "GET" && url.pathname === "/api/events" && session) {
      res.writeHead(200, {
        "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive",
      });
      res.write(": connected\n\n"); session.clients.add(res);
      // Replay card and status events sent before the browser connected.
      for (const event of session.events as { type: string; data: object }[]) {
        if (!event.type.startsWith("ui.")) continue;
        res.write(`data: ${JSON.stringify({ type: event.type.slice(3), data: event.data })}\n\n`);
      }
      req.on("close", () => session.clients.delete(res)); return;
    }
    if (req.method === "GET" && url.pathname === "/api/run" && session) {
      json(res, 200, { id: session.id, closed: session.closed, voice: session.voice(), events: session.events }); return;
    }
    if (req.method === "POST" && url.pathname === "/api/close" && session) {
      json(res, 200, { confirmed: await session.close() }); return;
    }
    json(res, 404, { error: "Not found." });
  } catch (error) {
    // Error responses name the failed operation without request headers or keys.
    json(res, 500, { error: error instanceof Error ? error.message : "Request failed." });
  }
});

async function createSession(req: http.IncomingMessage, res: http.ServerResponse) {
  const body = await bodyJson(req);
  if (typeof body.sdp !== "string" || !body.sdp.startsWith("v=0") || typeof body.timeZone !== "string") {
    json(res, 400, { error: "Supply an SDP offer and IANA time zone." }); return;
  }
  const dateParts = { timeZone: body.timeZone, year: "numeric", month: "2-digit", day: "2-digit" } as const;
  const today = new Intl.DateTimeFormat("en-CA", dateParts).format(new Date());
  const response = await fetch("https://api.openai.com/v1/live/sessions", {
    method: "POST", headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      session: {
        model: settings.voice_model, instructions: prompt, delegation: { type: "client" },
        // The server owns every command over the sideband; the browser only listens.
        client: { data_channel: { allowed_client_events: [], allowed_server_events: browserEvents } },
      },
      transport: { type: "webrtc", sdp: body.sdp },
    }),
    signal: AbortSignal.timeout(25_000),
  });
  if (!response.ok) {
    // The browser gets the status and a generic message; OpenAI's error text goes only to the server log.
    console.error("Live session creation failed", response.status, await response.text());
    json(res, response.status, { error: "Live session creation failed. See the server log." }); return;
  }
  const created = await response.json() as { session: { id: string }; transport: { sdp: string } };
  const id = created.session.id;
  const events: object[] = [];
  const clients = new Set<http.ServerResponse>();
  const record: RecordEvent = (type, data) => { events.push({ type, data, at: Date.now() }); };
  const publish: RecordEvent = (type, data) => {
    record("ui." + type, data);
    const chunk = `data: ${JSON.stringify({ type, data })}\n\n`;
    for (const client of clients) client.write(chunk);
  };
  const ws = new WebSocket(`wss://api.openai.com/v1/live/sessions/${encodeURIComponent(id)}/attach`, {
    headers: { Authorization: `Bearer ${apiKey}` }, handshakeTimeout: 10_000,
  });
  const send = (event: object) => {
    if (ws.readyState !== WebSocket.OPEN) throw new Error("Sideband is unavailable.");
    ws.send(JSON.stringify(event));
  };
  const backend = createBackend({ today, models: settings, record });
  const prepareUpdate = createUpdatePreparer({ voiceModel: settings.voice_model, researchModel: settings.research_model, effort: settings.research_effort, record });
  const controller = new TaskController({ backend, prepareUpdate, send, record, publish });
  let closing = false, resolveClosed!: (confirmed: boolean) => void;
  const closed = new Promise<boolean>(resolve => { resolveClosed = resolve; });
  // The documented shutdown: session.close, then wait for session.closed and its final usage. If it
  // never arrives, closing the sideband records the unconfirmed finalization, and the browser closing
  // its peer connection ends the session.
  const session: Session = {
    id, events, clients, closed: false, voice: () => controller.voiceSnapshot(),
    close: async () => {
      if (!closing) {
        closing = true; controller.close();
        if (ws.readyState === WebSocket.OPEN) {
          const command = { type: "session.close", event_id: crypto.randomUUID() };
          record("live.command", command); send(command);
        }
      }
      const confirmed = await Promise.race([closed, new Promise<boolean>(r => setTimeout(r, 15_000, false).unref())]);
      // terminate() emits 'close' at once; its handler records the unconfirmed finalization and persists
      // before `closed` resolves, so the run is saved even on Ctrl-C.
      if (!confirmed) ws.terminate();
      return closed;
    },
  };
  // Install all receivers before waiting for open or returning the SDP answer.
  ws.on("message", bytes => {
    let event;
    try { event = JSON.parse(bytes.toString()); } catch { return; }
    if (["session.input_audio.append", "session.output_audio.delta"].includes(event.type)) return;
    record("live.event", event);
    const ownedAppend = controller.receive(event);
    if (event.type === "session.closed") {
      session.closed = true; controller.close(); persist(session); resolveClosed(true); ws.close();
    }
    if (event.type === "error" && !ownedAppend) {
      const message = event.error?.message ?? "Live command failed.";
      publish("error", { message, code: event.error?.code, client_event_id: event.error?.client_event_id });
    }
  });
  // 'close' always follows 'error' and is the single teardown path.
  ws.on("error", error => record("sideband.error", { message: error.message }));
  ws.on("close", (code, reason) => {
    record("sideband.closed", { code, reason: reason.toString() });
    controller.close(); resolveClosed(session.closed);
    if (!session.closed) {
      record("finalization.unconfirmed", {});
      const message = "Lost the server connection to this session. Closing it.";
      if (!closing) publish("error", { message, fatal: true });
      persist(session);
    }
    clients.forEach(client => client.end());
    setTimeout(() => sessions.delete(id), 60_000).unref();
  });
  try { await once(ws, "open"); } catch (error) {
    throw new Error(`Sideband attachment failed: ${error instanceof Error ? error.message : error}`);
  }
  if (res.destroyed) { record("startup.abandoned", {}); await session.close(); return; }
  sessions.set(id, session);
  record("session.created", { session_id: id, today, timeZone: body.timeZone, settings });
  json(res, 201, created);
}

function json(res: http.ServerResponse, status: number, data: unknown) {
  res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" });
  res.end(JSON.stringify(data));
}
async function bodyJson(req: http.IncomingMessage) {
  let body = "";
  for await (const chunk of req) { body += chunk; if (body.length > 100_000) throw new Error("Request too large."); }
  return JSON.parse(body);
}
// Synchronous, so a run is on disk before a Ctrl-C exit.
function persist(session: Session) {
  mkdirSync(root + "evals/runs", { recursive: true });
  const run = { id: session.id, closed: session.closed, voice: session.voice(), events: session.events };
  writeFileSync(root + "evals/runs/" + session.id + ".json", JSON.stringify(run, null, 2));
}
server.listen(port, "127.0.0.1", () => console.log(`Voice research app: ${origin}`));
process.on("SIGINT", () => {
  void Promise.allSettled([...sessions.values()].map(s => s.close())).then(() => process.exit(0));
});
