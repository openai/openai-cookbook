import { pathToFileURL } from "node:url";
import { createInterface } from "node:readline";
import { stdin, stdout } from "node:process";
import { redact, TextOutput, type EventUpdate } from "./events.js";
import { workspacePath } from "./openshell.js";
import { readCredentials, SandboxSession } from "./session.js";

export type Command =
  | { kind: "prompt"; text: string }
  | { kind: "download"; path: string }
  | { kind: "status" | "logs" | "quit" | "empty" };

export function parseCommand(line: string): Command {
  const text = line.trim();
  if (!text) return { kind: "empty" };
  if (!text.startsWith("/")) return { kind: "prompt", text };
  const [command] = text.split(/\s/u, 1);
  const rest = text.slice(command?.length ?? 0).trim();
  if (command === "/download" && rest) return { kind: "download", path: workspacePath(rest) };
  if (!rest) {
    if (command === "/status") return { kind: "status" };
    if (command === "/logs") return { kind: "logs" };
    if (command === "/quit") return { kind: "quit" };
  }
  throw new Error("Commands: /status, /logs, /download <path>, /quit");
}

async function main() {
  const credentials = readCredentials();
  const print = (text: string) => { stdout.write(text + "\n"); };
  const safe = (text: string) => redact(text, session.sensitiveValues);
  const output = new TextOutput(safe, (text) => { stdout.write(text); });
  const onEvent = (event: EventUpdate) => {
    if (event.kind === "text") {
      if (event.phase === "delta") output.delta(event.part, event.text);
      else output.done(event.part, event.text);
    }
    if (event.kind === "command") {
      if (event.phase === "started") print(`\n[command] ${safe(event.command)}`);
      else if (event.exitCode !== null) print(`\n[command exit ${event.exitCode}]`);
    }
  };
  const session = new SandboxSession({ ...credentials, onEvent, onNotice: (text) => print(safe(text)) });
  let readline: ReturnType<typeof createInterface> | undefined;
  let operatorBusy = false;
  let quitting = false;

  function quit() {
    quitting = true;
    readline?.close();
    void session.stop();
  }
  function onInterrupt() {
    if (!session.active || session.cancelling) {
      quit();
      return;
    }
    print("\nRequesting turn cancellation. Press Ctrl-C again to quit.");
    void session.cancelTurn().catch((error: Error) => print(safe(error.message)));
  }

  process.on("SIGINT", onInterrupt);
  process.on("SIGTERM", quit);
  try {
    await session.start();
    print("Executor connected. Commands: /status, /logs, /download <path>, /quit");
    readline = createInterface({ input: stdin, output: stdout, prompt: "you> ", historySize: 0 });
    readline.on("SIGINT", onInterrupt);
    readline.on("close", quit);

    const prompt = () => {
      if (!quitting && !operatorBusy && !session.active) readline?.prompt();
    };

    async function handle(line: string) {
      const command = parseCommand(line);
      if (command.kind === "empty") return;
      if (command.kind === "quit") {
        quit();
        return;
      }
      if (command.kind === "status") {
        print(session.status);
        return;
      }
      if (operatorBusy || session.active) {
        print("A turn or operator command is in progress. Ctrl-C cancels an active turn.");
        return;
      }

      operatorBusy = true;
      try {
        switch (command.kind) {
          case "prompt": {
            const outcome = await session.runTurn(command.text);
            output.flush();
            print(outcome === "completed" ? "" : `\nTurn ${outcome}.`);
            break;
          }
          case "logs":
            try {
              print(safe(await session.sandbox.logs()).trimEnd() || "No sandbox logs yet.");
            } catch {
              print("Could not read sandbox logs.");
            }
            break;
          case "download": {
            const artifact = await session.sandbox.download(command.path);
            print(safe(`Downloaded to ${artifact.path}`));
            break;
          }
        }
      } finally {
        operatorBusy = false;
      }
    }

    readline.on("line", (line) => {
      if (quitting) return;
      void handle(line).catch((error: Error) => {
        if (!quitting) print(safe(error.message));
      }).finally(prompt);
    });
    prompt();
    const reason = await session.closing;
    if (reason) {
      print(safe(`\n${reason}`));
      process.exitCode = 1;
    }
  } catch (error) {
    if (!quitting) {
      const reason = await session.closing;
      print(safe(reason ?? (error instanceof Error ? error.message : "Could not start session.")));
      process.exitCode = 1;
    }
  } finally {
    quitting = true;
    readline?.close();
    // A paused stdin pipe can keep the CLI alive after readline closes.
    stdin.destroy();
    if (!await session.stop()) process.exitCode = 1;
    process.off("SIGINT", onInterrupt);
    process.off("SIGTERM", quit);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: Error) => {
    console.error(redact(error.message, Object.values(process.env).filter((value): value is string =>
      value !== undefined && value.startsWith("sk-"))));
    process.exitCode = 1;
  });
}
