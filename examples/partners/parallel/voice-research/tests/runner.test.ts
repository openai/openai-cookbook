import { createHash } from "node:crypto";
import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdtemp, readFile, rm, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Exercise the actual CLI with a local page standing in for the provider-backed UI.
// No API keys, requests, or real audio conversations are used.
test("CLI failures exit nonzero and retain server evidence when audio decoding fails", async () => {
  const directory = await mkdtemp(join(tmpdir(), "voice-runner-test-"));
  const fixtures = join(directory, "fixtures");
  await mkdir(fixtures);
  const bytes = Buffer.from("Mock fixture, never sent to a provider.");
  await writeFile(join(fixtures, "request.wav"), bytes);
  await writeFile(
    join(fixtures, "manifest.json"),
    JSON.stringify([
      { id: "request", file: "request.wav", text: "Mock", sha256: createHash("sha256").update(bytes).digest("hex") },
    ]),
  );
  const server = http.createServer((req, res) => {
    if (req.url?.startsWith("/api/run")) {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ closed: true, events: [{ type: "retained-evidence", data: { marker: "kept" } }] }));
      return;
    }
    res.setHeader("Content-Type", "text/html");
    res.end(`<script>
      window.cookbook={start:async()=>{},close:async()=>{},recording:async()=>btoa('invalid audio'),snapshot:()=>({sessionId:'test_session',recordingStart:0,closed:true,events:[{type:'ui.task',data:{task_id:'A',revision:1,version:1,state:'failed'}}]})};
    </script>`);
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  try {
    const port = (server.address() as { port: number }).port;
    const env = { ...process.env };
    delete env.OPENAI_API_KEY;
    delete env.PARALLEL_API_KEY;
    let code = 0;
    try {
      await promisify(execFile)(
        process.execPath,
        [
          "scripts/evaluate.ts",
          `--origin=http://127.0.0.1:${port}`,
          "--scenario=normal",
          `--fixtures=${fixtures}`,
          `--out=${join(directory, "run")}`,
        ],
        { cwd: new URL("../", import.meta.url), env, timeout: 30_000 },
      );
    } catch (error: any) {
      code = error.code;
    }
    assert.equal(code, 1, "a saved failed trial must fail the process");
    const trial = JSON.parse(await readFile(join(directory, "run/001-normal-trial.json"), "utf8"));
    assert.equal(trial.status, "failed");
    assert.equal(trial.server.events[0].type, "retained-evidence");
    assert(trial.errors.some((e: string) => /audio|recording|decode/i.test(e)));
    assert(JSON.parse(await readFile(join(directory, "run/001-normal-annotation.json"), "utf8")));
  } finally {
    server.closeAllConnections();
    server.close();
    await rm(directory, { recursive: true, force: true });
  }
});

// Real browser playback and the real CLI exercise readiness and scenario selection.
// A short generated tone is a transport fixture, not evidence of intelligible speech.
function tone() {
  const samples = 4000,
    bytes = Buffer.alloc(44 + samples * 4);
  bytes.write("RIFF");
  bytes.writeUInt32LE(bytes.length - 8, 4);
  bytes.write("WAVEfmt ", 8);
  bytes.writeUInt32LE(16, 16);
  bytes.writeUInt16LE(1, 20);
  bytes.writeUInt16LE(2, 22);
  bytes.writeUInt32LE(16000, 24);
  bytes.writeUInt32LE(64000, 28);
  bytes.writeUInt16LE(4, 32);
  bytes.writeUInt16LE(16, 34);
  bytes.write("data", 36);
  bytes.writeUInt32LE(samples * 4, 40);
  for (let n = 0; n < samples; n++)
    for (let ch = 0; ch < 2; ch++) bytes.writeInt16LE(Math.round(5000 * Math.sin(n * 0.2)), 44 + n * 4 + ch * 2);
  return bytes;
}
async function runMock(mode: "delayed" | "reverse" | "race" | "close-timeout" | "cleanup-failure") {
  const directory = await mkdtemp(join(tmpdir(), "voice-runner-test-"));
  const fixtures = join(directory, "fixtures");
  await mkdir(fixtures);
  const bytes = tone();
  const ids = ["request", "two-tasks", "target-correction"];
  await writeFile(join(fixtures, "tone.wav"), bytes);
  await writeFile(
    join(fixtures, "manifest.json"),
    JSON.stringify(
      ids.map(id => ({
        id,
        file: "tone.wav",
        text: "Test tone",
        sha256: createHash("sha256").update(bytes).digest("hex"),
      })),
    ),
  );
  let events: any[] = [],
    started = 0,
    closed = false,
    closedAt = 0;
  const server = http.createServer(async (req, res) => {
    if (req.url === "/events") {
      const parts = [];
      for await (const part of req) parts.push(part);
      events = JSON.parse(Buffer.concat(parts).toString());
      started ||= Date.now();
      res.end("ok");
      return;
    }
    if (req.url === "/close") {
      closed = true;
      closedAt = Date.now();
      res.end("ok");
      return;
    }
    if (req.url?.startsWith("/api/run")) {
      const latest = new Map(events.filter(e => e.type === "ui.task").map(e => [e.data.task_id, e.data]));
      const accepted = mode !== "delayed" || Date.now() - started >= 7200;
      const updates = [...latest.values()]
        .filter(t => t.state === "completed")
        .map(t => ({
          id: t.task_id,
          task_id: t.task_id,
          revision: t.revision,
          conclusion: 1,
          purpose: "finding",
          kind: "final",
          type: "session.thinking.append",
          state: accepted ? "accepted" : "preparing",
          chunks: accepted ? [{ event_id: t.task_id, state: "accepted" }] : [],
          updated_at: started + (mode === "delayed" ? 7200 : 0),
        }));
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ closed, events, voice: { version: 1, updates } }));
      return;
    }
    res.setHeader("Content-Type", "text/html");
    res.end(`<script>
      const mode=${JSON.stringify(mode)}; const events=[{type:"session.created",data:{today:"2026-11-03"}}]; let closed=false, count=0;
      const eventTask={request:'Events',location:'San Francisco',date:'2026-11-07',constraints:[]};
      const otherTask={request:'Compare software',location:null,date:null,constraints:[]};
      function add(id,task,revision,state,version) {events.push({type:'ui.task',client_ms:performance.now(),data:{task_id:id,task,revision,state,version,conclusion_version:1}});}
      async function save(){await fetch('/events',{method:'POST',body:JSON.stringify(events)});}
      window.cookbook={
        start:async()=>{
          await navigator.mediaDevices.getUserMedia({audio:true});
          const play=window.evalPlay;
          window.evalPlay=async(encoded,target)=>{
            if(mode==='race' && target) {add('events',eventTask,1,'completed',2); await save();}
            const result=await play(encoded,target); count++;
            if(mode==='reverse'||mode==='race') {
              if(count===1) {add('software',otherTask,1,'researching',1);add('events',eventTask,1,'researching',1);}
              else {
                add('events',{...eventTask,date:'2026-11-08',constraints:['indoors']},2,'researching',2);
                // The correction reaches the running research with its next request, as a real run logs it.
                events.push({type:'research.revision_applied',data:{task_id:'events',revision:2,via:'next_request',response_id:'r2'}});
                add('events',{...eventTask,date:'2026-11-08',constraints:['indoors']},2,'completed',3);add('software',otherTask,1,'completed',2);
              }
            } else {add('events',eventTask,1,'completed',1);}
            events.push({type:'live.event',client_ms:performance.now(),data:{type:'session.output_transcript.delta',delta:'Mock output'}});
            await save();return result;
          };
        },
        close:async()=>{if(mode==='close-timeout') await new Promise(()=>{}); closed=true;await fetch('/close');},
        recording:async()=>${JSON.stringify(bytes.toString("base64"))},
        snapshot:()=>({sessionId:'mock',recordingStart:0,closed,events})
      };
    </script>`);
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  try {
    const port = (server.address() as { port: number }).port;
    const scenario = mode === "reverse" || mode === "race" ? "multi-task-correction" : "normal";
    const env = { ...process.env };
    delete env.OPENAI_API_KEY;
    delete env.PARALLEL_API_KEY;
    const preload = join(directory, "cleanup.mjs");
    const moduleUrl = new URL("../node_modules/playwright/index.mjs", import.meta.url).href;
    await writeFile(
      preload,
      `import { chromium } from ${JSON.stringify(moduleUrl)};
      const launch=chromium.launch.bind(chromium);
      chromium.launch=async(...args)=>{const browser=await launch(...args);const create=browser.newContext.bind(browser);
        browser.newContext=async(...args)=>{const context=await create(...args);const close=context.close.bind(context);
          context.close=async()=>{await close();throw new Error('Controlled cleanup failure');};return context;};return browser;};`,
    );
    const preloads = mode === "cleanup-failure" ? ["--import", preload] : [];
    let code = 0;
    try {
      await promisify(execFile)(
        process.execPath,
        [
          ...preloads,
          "scripts/evaluate.ts",
          `--origin=http://127.0.0.1:${port}`,
          `--scenario=${scenario}`,
          `--fixtures=${fixtures}`,
          `--out=${join(directory, "run")}`,
        ],
        { cwd: new URL("../", import.meta.url), env, timeout: 45_000 },
      );
    } catch (error: any) {
      code = error.code;
    }
    const trial = JSON.parse(await readFile(join(directory, `run/001-${scenario}-trial.json`), "utf8"));
    assert(await readFile(join(directory, `run/001-${scenario}-annotation.json`), "utf8"));
    return { code, trial, elapsed: closedAt - started };
  } finally {
    server.closeAllConnections();
    server.close();
    await rm(directory, { recursive: true, force: true });
  }
}
test("CLI waits for preparation longer than six seconds and drains after final acceptance", async () => {
  const result = await runMock("delayed");
  assert.equal(result.code, 0, JSON.stringify(result.trial.errors));
  assert.equal(result.trial.status, "completed");
  assert(result.elapsed >= 13200, "early transcript cannot close a pending final");
});
test("CLI targets the event task even when software appears first", async () => {
  const { code, trial } = await runMock("reverse");
  assert.equal(code, 0, JSON.stringify(trial.errors));
  assert.equal(trial.fixture_playback[1].trigger.task_id, "events");
  assert.equal(trial.fixture_playback[1].trigger.revision, 1);
  assert.equal(trial.fixture_playback[1].trigger.state, "researching");
});
test("CLI rejects a target that finishes between polling and playback", async () => {
  const { code, trial } = await runMock("race");
  assert.equal(code, 1);
  assert(trial.errors.some((e: string) => e.includes("Scenario window not exercised")));
});
test("CLI retains evidence and annotations when session close times out", async () => {
  const { code, trial } = await runMock("close-timeout");
  assert.equal(code, 1);
  assert(trial.errors.some((e: string) => e.includes("Session close timed out")));
  assert(trial.server.events.length > 0);
  assert(trial.recording_check.pass);
});

test("CLI writes evidence after browser context cleanup fails", async () => {
  const { code, trial } = await runMock("cleanup-failure");
  assert.equal(code, 1);
  assert(trial.errors.some((e: string) => e.includes("Controlled cleanup failure")));
  assert(trial.server.closed);
  assert(trial.recording_check.pass);
});
