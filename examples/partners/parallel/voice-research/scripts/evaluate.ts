import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { chromium, type Page } from "playwright";
import { deliveryChecks, structuralChecks, type Annotation, type LogEvent, type Trial } from "./evaluation.ts";
import { checkRecording } from "./recording.ts";

type Snapshot = { sessionId: string | null; events: LogEvent[]; recordingStart: number | null; closed: boolean };
declare global {
  interface Window {
    cookbook: {
      start: (options?: { capture: boolean }) => Promise<void>;
      close: () => Promise<void>;
      snapshot: () => Snapshot;
      recording: () => Promise<string | null>;
    };
    evalPlay: (
      encoded: string,
      target?: { task_id: string; revision: number },
    ) => Promise<{ start_ms: number; end_ms: number; trigger?: unknown }>;
  }
}
type Fixture = { id: string; text: string; file: string; sha256: string; synthetic?: boolean };
type Step = { fixture: string; after_task_count?: number; target_location?: string; state?: string };
type Scenario = {
  id: string;
  steps: Step[];
  task_count: number;
  cancelled_count: number;
  correction: boolean;
  correct_during_research?: boolean;
  required: string;
  forbidden: string;
  evidence: string;
};
const { values } = parseArgs({
  options: {
    origin: { type: "string", default: "http://localhost:3000" },
    out: { type: "string" },
    fixtures: { type: "string" },
    repeat: { type: "string", default: "1" },
    scenario: { type: "string" },
  },
});
const repetitions = Number(values.repeat);
if (!Number.isInteger(repetitions) || repetitions < 1 || repetitions > 20)
  throw new Error("Use --repeat=1..20. Start with one; each run consumes paid API usage.");
const origin = new URL(values.origin!).origin;
if (!["localhost", "127.0.0.1"].includes(new URL(origin).hostname))
  throw new Error("Run this local tutorial against localhost or 127.0.0.1.");
const root = fileURLToPath(new URL("../", import.meta.url));
const fixtureRoot = resolve(values.fixtures ?? join(root, "evals/fixtures"));
const fixtures = JSON.parse(await readFile(join(fixtureRoot, "manifest.json"), "utf8")) as Fixture[];
const allScenarios = JSON.parse(await readFile(join(root, "evals/scenarios.json"), "utf8")) as Scenario[];
const scenarios = allScenarios.filter(scenario => !values.scenario || scenario.id === values.scenario);
if (!scenarios.length) throw new Error(`Unknown scenario. Choose one of: ${allScenarios.map(s => s.id).join(", ")}.`);
const audio = new Map<string, string>();
for (const id of new Set(scenarios.flatMap(scenario => scenario.steps.map(step => step.fixture)))) {
  const fixture = fixtures.find(fixture => fixture.id === id);
  if (!fixture) throw new Error(`Missing fixture ${id}; run node scripts/generate-fixtures.ts first.`);
  const bytes = await readFile(join(fixtureRoot, fixture.file)).catch(() => {
    throw new Error(
      `Missing audio fixture ${fixture.file}. Generate fixtures with node scripts/generate-fixtures.ts on macOS, or supply recordings and manifest hashes with --fixtures. See evals/README.md.`,
    );
  });
  if (createHash("sha256").update(bytes).digest("hex") !== fixture.sha256)
    throw new Error(`Fixture hash mismatch: ${id}. Update manifest after replacing a recording.`);
  audio.set(id, bytes.toString("base64"));
}
const out = resolve(values.out ?? join(root, "evals/results", new Date().toISOString().replaceAll(":", "-")));
await mkdir(dirname(out), { recursive: true });
await mkdir(out); // Preserve earlier attempts, including partial failures.
const configuration: Record<string, string> = {};
for (const file of [
  "settings.json",
  "package-lock.json",
  "src/server.ts",
  "src/controller.ts",
  "src/live-updates.ts",
  "src/backend.ts",
  "src/research.ts",
  "src/types.ts",
  "public/app.js",
  "public/index.html",
  "public/style.css",
  "evals/scenarios.json",
  "evals/rates.json",
  "scripts/evaluate.ts",
  "scripts/evaluation.ts",
  "scripts/recording.ts",
]) {
  configuration[file] = createHash("sha256")
    .update(await readFile(join(root, file)))
    .digest("hex");
}
await writeFile(
  join(out, "configuration.json"),
  JSON.stringify(
    {
      created_at: new Date().toISOString(),
      origin,
      repetitions,
      settings: JSON.parse(await readFile(join(root, "settings.json"), "utf8")),
      file_hashes: configuration,
      fixtures,
      scenarios,
    },
    null,
    2,
  ),
);
const browser = await chromium.launch({ headless: true, args: ["--autoplay-policy=no-user-gesture-required"] });

async function bounded<T>(promise: Promise<T>, label: string, timeout = 20_000): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  try {
    return await Promise.race([
      promise,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${label} timed out.`)), timeout);
      }),
    ]);
  } finally {
    clearTimeout(timer!);
  }
}

async function awaitSpeech(page: Page, scenario: Scenario, sessionId: string) {
  const deadline = Date.now() + 150_000;
  while (Date.now() < deadline) {
    const quiet = await bounded(
      page.evaluate(
        ({ count, cancelled }) => {
          const events = window.cookbook.snapshot().events;
          const latest = new Map<string, any>();
          for (const e of events) if (e.type === "ui.task") latest.set(String(e.data.task_id), e);
          const tasks = [...latest.values()];
          if (tasks.some(e => e.data.state === "failed")) throw new Error("Research failed.");
          const error = events.find(e => e.type === "ui.error");
          if (error) throw new Error(String(error.data.message));
          if (
            tasks.length !== count ||
            tasks.some(e => !["completed", "cancelled"].includes(e.data.state)) ||
            tasks.filter(e => e.data.state === "cancelled").length !== cancelled
          )
            return false;
          const last = events
            .filter(e => e.type === "live.event" && e.data.type === "session.output_transcript.delta")
            .at(-1);
          return !!last && performance.now() - Math.max(last.client_ms!, ...tasks.map(e => e.client_ms ?? 0)) > 6000;
        },
        { count: scenario.task_count, cancelled: scenario.cancelled_count },
      ),
      "Transcript snapshot",
    );
    // The complete run contains transcripts and search excerpts. Fetch it only once the
    // browser has finished speaking, then verify the server accepted every required update.
    if (quiet) {
      const response = await page.context().request.get(origin + "/api/run?id=" + encodeURIComponent(sessionId), { timeout: 5_000 });
      if (!response.ok()) throw new Error(`Delivery snapshot HTTP ${response.status()}.`);
      const proof = deliveryChecks({ server: await response.json() });
      if (proof.issues.length) throw new Error(proof.issues.join(" "));
      if (proof.ready && Date.now() - proof.accepted_at > 6000) return;
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error("Timed out waiting for accepted voice updates and the transcript drain.");
}

async function trial(scenario: Scenario, repetition: number, index: number) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors: string[] = [];
  const result: Trial & Record<string, unknown> = {
    scenario: scenario.id,
    status: "failed",
    recording_file: null,
    errors,
    client: { events: [], recordingStart: null },
    server: null,
    repetition,
    expectations: {
      task_count: scenario.task_count,
      cancelled_count: scenario.cancelled_count,
      correction: scenario.correction,
      correct_during_research: scenario.correct_during_research ?? false,
      required: scenario.required,
      forbidden: scenario.forbidden,
      evidence: scenario.evidence,
    },
    fixture_playback: [],
  };
  const playback: { fixture: string; start_ms: number; end_ms: number; trigger_revision?: unknown }[] = [];
  const prefix = `${String(index).padStart(3, "0")}-${scenario.id}`;
  page.on("pageerror", error => errors.push(error.message));
  page.on("response", response => {
    if (new URL(response.url()).pathname.startsWith("/api/") && !response.ok())
      errors.push(`HTTP ${response.status()} ${new URL(response.url()).pathname}`);
  });
  let sessionId: string | null = null;
  try {
    await page.addInitScript(() => {
      navigator.mediaDevices.getUserMedia = async () => {
        const audio = new AudioContext();
        await audio.resume();
        const destination = audio.createMediaStreamDestination();
        const oscillator = audio.createOscillator();
        const gain = audio.createGain();
        gain.gain.value = 0;
        oscillator.connect(gain).connect(destination);
        oscillator.start();
        window.evalPlay = async (encoded, target) => {
          const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
          const source = audio.createBufferSource();
          source.buffer = await audio.decodeAudioData(bytes.buffer);
          source.connect(destination);
          const latest = new Map<string, any>();
          for (const e of window.cookbook.snapshot().events)
            if (e.type === "ui.task") latest.set(String(e.data.task_id), e.data);
          const trigger = target ? latest.get(target.task_id) : undefined;
          if (target && (!trigger || trigger.state !== "researching" || trigger.revision !== target.revision))
            throw new Error("Scenario window not exercised: target finished or changed before playback.");
          const start_ms = performance.now();
          await new Promise<void>(resolve => {
            source.onended = () => resolve();
            source.start();
          });
          return { start_ms, end_ms: performance.now(), trigger };
        };
        return destination.stream;
      };
    });
    await page.goto(origin);
    await page.evaluate(() => window.cookbook.start({ capture: true }));
    const initial = await page.evaluate(() => window.cookbook.snapshot());
    sessionId = initial.sessionId;
    if (!sessionId) throw new Error("No session ID after start.");
    console.log(JSON.stringify({ scenario: scenario.id, repetition, session_id: sessionId, stage: "ready" }));
    for (const step of scenario.steps) {
      let target: { task_id: string; revision: number } | undefined;
      if (step.after_task_count) {
        const handle = await page.waitForFunction(
          step => {
            const latest = new Map<string, any>();
            for (const e of window.cookbook.snapshot().events)
              if (e.type === "ui.task") latest.set(String(e.data.task_id), e.data);
            const tasks = [...latest.values()];
            const matches = tasks.filter(t => !step.target_location || t.task.location === step.target_location);
            return tasks.length >= step.after_task_count! &&
              matches.length === 1 &&
              (!step.state || matches[0].state === step.state)
              ? matches[0]
              : false;
          },
          step,
          { timeout: 40_000, polling: 20 },
        );
        target = (await handle.jsonValue()) as { task_id: string; revision: number };
        await handle.dispose();
      }
      playback.push({
        fixture: step.fixture,
        ...(await bounded(
          page.evaluate(({ encoded, target }) => window.evalPlay(encoded, target), {
            encoded: audio.get(step.fixture)!,
            target,
          }),
          "Fixture playback",
          45_000,
        )),
      });
    }
    await awaitSpeech(page, scenario, sessionId);
    result.status = "completed";
  } catch (error) {
    errors.push(error instanceof Error ? error.message : String(error));
  } finally {
    async function collect(label: string, action: () => Promise<void>) {
      try {
        await action();
      } catch (error) {
        errors.push(`${label}: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
    await collect("Snapshot before close", async () => {
      sessionId ??= (
        await bounded(
          page.evaluate(() => window.cookbook.snapshot()),
          "Snapshot",
        )
      ).sessionId;
    });
    await collect("Close", async () => {
      if (sessionId)
        await bounded(
          page.evaluate(() => window.cookbook.close()),
          "Session close",
        );
    });
    await collect("Browser snapshot", async () => {
      result.client = await bounded(
        page.evaluate(() => window.cookbook.snapshot()),
        "Browser snapshot",
      );
    });
    await collect("Server evidence", async () => {
      if (!sessionId) return;
      const response = await context.request.get(origin + "/api/run?id=" + encodeURIComponent(sessionId), {
        timeout: 5_000,
      });
      if (!response.ok()) throw new Error(`Run export HTTP ${response.status()}.`);
      result.server = await response.json();
    });
    await collect("Audio recording", async () => {
      const recording = await bounded(
        page.evaluate(() => window.cookbook.recording()),
        "Recording export",
      );
      if (!recording) throw new Error("Client audio recording is missing.");
      result.recording_file = prefix + ".webm";
      await writeFile(join(out, result.recording_file), Buffer.from(recording, "base64"));
      result.recording_check = await checkRecording(join(out, result.recording_file));
      if (!result.recording_check.pass)
        throw new Error("Saved microphone or speaker channel has less than 100 ms of audio.");
    });
    await collect("Browser cleanup", async () => {
      await bounded(context.close(), "Browser cleanup", 5_000);
    });
    result.fixture_playback = playback;
    result.session_id = sessionId;
    const checks = structuralChecks(result);
    result.structure = checks;
    errors.push(...checks.issues);
    if (errors.length) {
      result.status = "failed";
      process.exitCode = 1;
    }
    const identities = new Map<string, any>();
    for (const e of result.server?.events ?? [])
      if (e.type === "ui.task") identities.set(`${e.data.task_id}:${e.data.revision}`, e.data);
    const annotation: Annotation = {
      tasks: [...identities.values()].map(d => ({
        task_id: d.task_id,
        revision: d.revision,
        request_end_ms: null,
        first_useful_speech_ms: null,
        final_speech_ms: null,
        task_completion_pass: null,
        quality_pass: null,
        correction_pass: null,
        cancellation_pass: null,
        cancelled: d.state === "cancelled",
        notes: "Unreviewed.",
      })),
      task_completion_pass: null,
      quality_pass: null,
      correction_pass: null,
      notes:
        "Unreviewed. Listen to the recording and inspect sources against the saved expectations. Grade fulfillment separately from answer quality. Timestamps are relative to recording start.",
    };
    await writeFile(join(out, prefix + "-trial.json"), JSON.stringify(result, null, 2));
    await writeFile(join(out, prefix + "-annotation.json"), JSON.stringify(annotation, null, 2));
    console.log(JSON.stringify({ scenario: scenario.id, repetition, status: result.status, errors }));
  }
}
try {
  let index = 0;
  for (let repetition = 1; repetition <= repetitions; repetition++)
    for (const scenario of scenarios) await trial(scenario, repetition, ++index);
} finally {
  await bounded(browser.close(), "Browser shutdown", 10_000);
}
console.log(
  `Saved runs and client playback recordings to ${out}. Task completion, quality, correction, and speech timing need annotation before reporting results.`,
);
