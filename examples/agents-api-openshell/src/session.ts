import { randomUUID } from "node:crypto";
import { setTimeout as sleep } from "node:timers/promises";
import OpenAI from "openai";
import { reduceEvent, type EventUpdate, type TurnOutcome } from "./events.js";
import { OpenShellSandbox, WORKSPACE } from "./openshell.js";

const CONNECTION_TIMEOUT_MS = 75_000;
const RECONNECTION_TIMEOUT_MS = 30_000;
const TURN_TIMEOUT_MS = 180_000;
const DEFAULT_MODEL = "gpt-6-astra";

export function readCredentials(env = process.env) {
  const applicationKey = env.OPENAI_API_KEY;
  const executorKey = env.OPENAI_EXECUTOR_API_KEY;
  const keyPattern = /^sk-[A-Za-z0-9_-]{16,}$/u;
  if (!applicationKey || !keyPattern.test(applicationKey)) {
    throw new Error("Set OPENAI_API_KEY to the application key.");
  }
  if (!executorKey || !keyPattern.test(executorKey)) {
    throw new Error("Set OPENAI_EXECUTOR_API_KEY to the restricted Agents environment key.");
  }
  if (applicationKey === executorKey) throw new Error("Use distinct application and environment keys.");
  return { applicationKey, executorKey };
}

export async function retryTransient<T>(
  action: () => Promise<T>,
  isTransient: (error: unknown) => boolean,
  delay = (ms: number) => sleep(ms),
): Promise<T> {
  const delays = [250, 1_000];
  for (const ms of delays) {
    try {
      return await action();
    } catch (error) {
      if (!isTransient(error)) throw error;
      await delay(ms);
    }
  }
  return action();
}

export async function cleanupResources(
  deleteSandbox: () => Promise<void>,
  deleteSession: () => Promise<void>,
) {
  const result = { sandbox: true, session: true };
  try {
    await deleteSandbox();
  } catch {
    result.sandbox = false;
  }
  try {
    await deleteSession();
  } catch {
    result.session = false;
  }
  return result;
}

export class TurnState {
  #rootStarted = false;
  #idle = false;
  #outcome?: TurnOutcome;

  get finished() {
    return this.#outcome !== undefined;
  }

  update(event: EventUpdate) {
    if (event.kind === "turn-started") this.#rootStarted = true;
    if (event.kind === "idle" && (this.#rootStarted || this.#outcome)) this.#idle = true;
    if (event.kind === "turn") this.#outcome = event.outcome;
    return this.#idle ? this.#outcome : undefined;
  }
}

type Turn = {
  state: TurnState;
  submitted: Promise<unknown>;
  result: PromiseWithResolvers<TurnOutcome | undefined>;
  cancellation?: Promise<void>;
};

type SessionOptions = ReturnType<typeof readCredentials> & {
  onEvent?: (event: EventUpdate) => void;
  onNotice?: (message: string) => void;
};

function statusOnly(error: unknown) {
  return error instanceof OpenAI.APIError && error.status ? ` (HTTP ${error.status})` : "";
}

export class SandboxSession {
  readonly sandbox = new OpenShellSandbox(`agent-os-${randomUUID().replaceAll("-", "").slice(0, 10)}`);
  readonly #client: OpenAI;
  readonly #abort = new AbortController();
  readonly #connected = Promise.withResolvers<boolean>();
  readonly #closing = Promise.withResolvers<string | undefined>();
  readonly closing = this.#closing.promise;
  #sessionId?: string;
  #remoteUrl?: string;
  #environment: "connecting" | "connected" | "reconnecting" = "connecting";
  #reconnectionDeadline?: NodeJS.Timeout;
  #sandboxRequested = false;
  #startup?: Promise<void>;
  #cleanup?: Promise<boolean>;
  #active?: Turn;
  #closingTurn?: Turn;

  constructor(private readonly options: SessionOptions, fetch?: typeof globalThis.fetch) {
    this.#client = new OpenAI({
      apiKey: options.applicationKey,
      baseURL: "https://api.openai.com/v1",
      maxRetries: 0,
      timeout: 12_000,
      logLevel: "off",
      fetch,
    });
  }

  get status() {
    return `Session: ${this.#sessionId ?? "creating"} | Sandbox: ${this.sandbox.name} | Executor: ${this.#environment} | Turn: ${
      this.cancelling ? "cancelling" : this.#active ? "active" : "idle"
    }`;
  }

  get active() { return this.#active !== undefined; }
  get cancelling() { return this.#active?.cancellation !== undefined; }
  get sensitiveValues() {
    return [this.options.applicationKey, this.options.executorKey, this.#remoteUrl ?? ""];
  }

  start(): Promise<void> {
    this.#abort.signal.throwIfAborted();
    return this.#startup ??= this.#start().catch((error: Error) => {
      this.#close(error.message);
      throw error;
    });
  }

  async #start() {
    const sessions = this.#client.beta.agents.sessions;
    const session = await sessions.create({
      agent: {
        model: DEFAULT_MODEL,
        instructions: "You are a terminal assistant. Use the shell and files in /workspace. When asked to create an artifact, put it in /workspace/outputs unless given a different workspace path. Never print credentials or inspect authentication state.",
      },
      environment: { type: "self_hosted", workspace_directory: WORKSPACE },
    }).catch((error: unknown) => {
      throw new Error(`Could not create the Agents API session${statusOnly(error)}.`);
    });
    this.#sessionId = session.id;
    this.#abort.signal.throwIfAborted();
    if (session.status === "failed") throw new Error("The Agents API created a failed session.");
    if (session.environment?.type !== "self_hosted" || !session.environment.remote_url) {
      throw new Error("The session did not return self-hosted connection details.");
    }
    this.#remoteUrl = session.environment.remote_url;
    this.options.onNotice?.(this.status);
    const stream = await sessions.events.stream(session.id, { signal: this.#abort.signal })
      .catch((error: unknown) => {
        throw new Error(`Could not open the Agents API event stream${statusOnly(error)}.`);
      });
    void this.#consume(stream);
    this.#abort.signal.throwIfAborted();
    // Record ownership before provisioning, since the gateway can create it before returning.
    this.#sandboxRequested = true;
    const deadline = setTimeout(() => {
      this.#close("Timed out waiting for executor registration. Check the environment key and OpenShell policy.");
    }, CONNECTION_TIMEOUT_MS);

    try {
      await this.sandbox.create(session.environment.id, this.#remoteUrl, this.options.executorKey)
        .catch(() => { throw new Error("OpenShell could not start the executor. Check the local gateway and image."); });
      this.#abort.signal.throwIfAborted();
      void this.#watchExecutor();
      if (!await this.#connected.promise) throw new Error("Executor did not connect.");
    } finally {
      clearTimeout(deadline);
    }
  }

  async #consume(stream: Awaited<ReturnType<OpenAI["beta"]["agents"]["sessions"]["events"]["stream"]>>) {
    try {
      for await (const event of stream) {
        const update = reduceEvent(event);
        if (!update) continue;
        if (update.kind === "connected") {
          if (this.#environment === "reconnecting") this.options.onNotice?.("Executor reconnected.");
          this.#environment = "connected";
          clearTimeout(this.#reconnectionDeadline);
          this.#connected.resolve(true);
        }
        if (update.kind === "fatal") {
          this.#close(update.message);
          return;
        }
        if (update.kind === "disconnected" && this.#environment === "connected") {
          this.#environment = "reconnecting";
          this.options.onNotice?.("Executor disconnected. Waiting for it to reconnect.");
          this.#reconnectionDeadline = setTimeout(
            () => this.#close("The OpenShell executor did not reconnect."), RECONNECTION_TIMEOUT_MS,
          );
        }
        this.options.onEvent?.(update);
        const outcome = this.#active?.state.update(update);
        if (outcome) this.#active?.result.resolve(outcome);
      }
    } catch {
      // A disconnected stream cannot replay events. End this local session and release resources.
    }
    if (!this.#abort.signal.aborted) this.#close("The Agents API event stream disconnected.");
  }

  async #watchExecutor() {
    const signal = this.#abort.signal;
    let lookupFailures = 0;
    while (!signal.aborted) {
      await sleep(3_000, undefined, { signal }).catch(() => {});
      if (signal.aborted) return;
      const phase = await this.sandbox.phase().catch(() => undefined);
      if (signal.aborted) return;
      if (phase === "Ready") {
        lookupFailures = 0;
      } else if (phase === "Error" || phase === "Stopped" || phase === "Completed") {
        this.#close(`The OpenShell executor exited (sandbox phase: ${phase}).`);
        return;
      } else if (++lookupFailures >= 3) {
        this.#close("Could not confirm the executor is running. Check the OpenShell gateway.");
        return;
      }
    }
  }

  async runTurn(text: string): Promise<TurnOutcome> {
    this.#abort.signal.throwIfAborted();
    const sessionId = this.#sessionId;
    if (!sessionId || this.#environment !== "connected") throw new Error("Executor is unavailable.");
    if (this.#active) throw new Error("A turn is already active.");
    const submitted = this.#client.beta.agents.sessions.events.create(sessionId, {
      "Idempotency-Key": randomUUID(),
      events: [{
        type: "agent.session.input.message",
        input: [{ role: "user", content: [{ type: "input_text", text }] }],
      }],
    });
    const turn: Turn = {
      state: new TurnState(),
      submitted,
      result: Promise.withResolvers(),
    };
    this.#active = turn;
    const deadline = setTimeout(() => this.#close("Timed out waiting for the Agents API turn to finish."), TURN_TIMEOUT_MS);

    try {
      try {
        await submitted;
      } catch (error) {
        this.#close(`The Agents API could not confirm prompt submission${statusOnly(error)}.`);
      }
      const outcome = await turn.result.promise;
      if (!outcome) throw new Error("The session closed before the turn finished.");
      return outcome;
    } finally {
      clearTimeout(deadline);
      await turn.cancellation?.catch(() => {});
      this.#active = undefined;
    }
  }

  async cancelTurn() {
    const turn = this.#active;
    const sessionId = this.#sessionId;
    if (!turn || !sessionId) return;
    const cancellation = turn.cancellation ??= this.#cancel(sessionId, turn);
    try {
      await cancellation;
    } catch (error) {
      if (turn.cancellation === cancellation) turn.cancellation = undefined;
      throw new Error(`The Agents API could not confirm cancellation${statusOnly(error)}.`);
    }
  }

  async #cancel(sessionId: string, turn: Turn) {
    // Wait for the input request before cancelling, even if its outcome was ambiguous.
    await turn.submitted.catch(() => {});
    if (turn.state.finished) return;
    await this.#client.beta.agents.sessions.events.create(sessionId, {
      events: [{ type: "agent.session.input.cancel" }],
    }, { timeout: 5_000 });
  }

  stop(): Promise<boolean> {
    this.#close();
    return this.#cleanup ??= this.#deleteResources();
  }

  #close(reason?: string) {
    if (this.#abort.signal.aborted) return;
    this.#abort.abort(new Error("Session is closing."));
    clearTimeout(this.#reconnectionDeadline);
    this.#connected.resolve(false);
    this.#closingTurn = this.#active;
    this.#closingTurn?.result.resolve(undefined);
    this.#closing.resolve(reason);
  }

  async #deleteResources() {
    // Let in-flight creation settle before deleting resources by ID.
    await this.#startup?.catch(() => {});
    const sessionId = this.#sessionId;
    const active = this.#closingTurn;
    if (active && sessionId) {
      await (active.cancellation ?? this.#cancel(sessionId, active)).catch(() => {});
    }
    const result = await cleanupResources(
      async () => {
        if (this.#sandboxRequested) await retryTransient(() => this.sandbox.delete(), () => true);
      },
      async () => {
        if (!sessionId) return;
        await retryTransient(async () => {
          try {
            const result = await this.#client.beta.agents.sessions.delete(sessionId, { timeout: 5_000 });
            if (!result.deleted) throw new Error("Deletion was unconfirmed.");
          } catch (error) {
            if (!(error instanceof OpenAI.APIError && error.status === 404)) throw error;
          }
        }, (error) => error instanceof OpenAI.APIConnectionError ||
          (error instanceof OpenAI.APIError && [409, 429, 500, 502, 503, 504].includes(error.status ?? 0)));
      },
    );
    if (!result.sandbox) {
      this.options.onNotice?.(`Sandbox deletion could not be confirmed. Run openshell sandbox delete ${this.sandbox.name}.`);
    }
    if (!result.session) {
      this.options.onNotice?.(`Session ${sessionId} could not be deleted. Retry deletion or contact OpenAI support for server-side repair.`);
    }
    return result.sandbox && result.session;
  }
}
