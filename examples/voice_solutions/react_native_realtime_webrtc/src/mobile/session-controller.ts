export type SessionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "paused"
  | "reconnecting"
  | "failed";

export interface RealtimeTransport {
  open(): Promise<void>;
  close(): Promise<void> | void;
  setUnexpectedCloseHandler(handler: (error?: Error) => void): void;
}

type TimerHandle = ReturnType<typeof setTimeout>;

export type SessionControllerOptions = {
  createTransport: () => RealtimeTransport;
  retryDelaysMs?: readonly number[];
  onStatus?: (status: SessionStatus, error?: Error) => void;
  setTimer?: (callback: () => void, delayMs: number) => TimerHandle;
  clearTimer?: (handle: TimerHandle) => void;
};

export class RealtimeSessionController {
  private readonly createTransport: () => RealtimeTransport;
  private readonly retryDelaysMs: readonly number[];
  private readonly onStatus?: SessionControllerOptions["onStatus"];
  private readonly setTimer: NonNullable<SessionControllerOptions["setTimer"]>;
  private readonly clearTimer: NonNullable<SessionControllerOptions["clearTimer"]>;

  private desired = false;
  private appActive = true;
  private generation = 0;
  private retryIndex = 0;
  private transport: RealtimeTransport | null = null;
  private connectPromise: Promise<void> | null = null;
  private retryTimer: TimerHandle | null = null;
  private status: SessionStatus = "idle";

  constructor(options: SessionControllerOptions) {
    this.createTransport = options.createTransport;
    this.retryDelaysMs = options.retryDelaysMs ?? [500, 1_000, 2_000];
    this.onStatus = options.onStatus;
    this.setTimer = options.setTimer ?? setTimeout;
    this.clearTimer = options.clearTimer ?? clearTimeout;
  }

  get currentStatus(): SessionStatus {
    return this.status;
  }

  start(): Promise<void> {
    this.desired = true;
    return this.ensureConnected();
  }

  async stop(): Promise<void> {
    this.desired = false;
    this.retryIndex = 0;
    this.generation += 1;
    this.connectPromise = null;
    this.cancelRetry();
    await this.closeCurrentTransport();
    this.setStatus("idle");
  }

  async setAppActive(active: boolean): Promise<void> {
    if (this.appActive === active) return;
    this.appActive = active;

    if (!active) {
      this.generation += 1;
      this.connectPromise = null;
      this.cancelRetry();
      await this.closeCurrentTransport();

      // AppState notifications are intentionally fire-and-forget in the
      // integration example. If a foreground notification arrived while the
      // asynchronous close was settling, reconnect now instead of overwriting
      // that newer state with "paused".
      if (this.appActive) {
        if (this.desired) {
          this.retryIndex = 0;
          this.setStatus("paused");
          await this.ensureConnected();
        } else {
          this.setStatus("idle");
        }
        return;
      }

      this.setStatus(this.desired ? "paused" : "idle");
      return;
    }

    if (this.desired) {
      this.retryIndex = 0;
      await this.ensureConnected();
    }
  }

  private ensureConnected(): Promise<void> {
    if (!this.desired || !this.appActive || this.status === "connected") {
      return Promise.resolve();
    }
    if (this.connectPromise) return this.connectPromise;

    const generation = ++this.generation;
    const transport = this.createTransport();
    this.transport = transport;
    transport.setUnexpectedCloseHandler((error) => {
      if (transport === this.transport) {
        void this.handleUnexpectedClose(error);
      }
    });

    this.setStatus(this.retryIndex > 0 ? "reconnecting" : "connecting");
    const attempt = transport
      .open()
      .then(async () => {
        if (
          generation !== this.generation ||
          !this.desired ||
          !this.appActive
        ) {
          await transport.close();
          return;
        }
        this.retryIndex = 0;
        this.setStatus("connected");
      })
      .catch(async (cause: unknown) => {
        await transport.close();
        if (generation !== this.generation) return;
        this.transport = null;
        this.scheduleRetry(asError(cause));
      })
      .finally(() => {
        if (this.connectPromise === attempt) this.connectPromise = null;
      });

    this.connectPromise = attempt;
    return attempt;
  }

  private async handleUnexpectedClose(error?: Error): Promise<void> {
    const pendingAttempt = this.connectPromise;
    this.generation += 1;
    await this.closeCurrentTransport();

    // A data-channel close can be reported before open() settles. Waiting for
    // that attempt prevents a retry timer from firing while connectPromise
    // still points at the stale attempt and then being lost permanently.
    await pendingAttempt;
    if (this.desired && this.appActive) {
      this.scheduleRetry(error ?? new Error("Realtime transport closed"));
    }
  }

  private scheduleRetry(error: Error): void {
    if (!this.desired || !this.appActive) return;

    const delay = this.retryDelaysMs[this.retryIndex];
    if (delay === undefined) {
      this.setStatus("failed", error);
      return;
    }

    this.retryIndex += 1;
    this.setStatus("reconnecting", error);
    this.cancelRetry();
    this.retryTimer = this.setTimer(() => {
      this.retryTimer = null;
      void this.ensureConnected();
    }, delay);
  }

  private async closeCurrentTransport(): Promise<void> {
    const current = this.transport;
    this.transport = null;
    if (current) await current.close();
  }

  private cancelRetry(): void {
    if (this.retryTimer) {
      this.clearTimer(this.retryTimer);
      this.retryTimer = null;
    }
  }

  private setStatus(status: SessionStatus, error?: Error): void {
    this.status = status;
    this.onStatus?.(status, error);
  }
}

function asError(cause: unknown): Error {
  return cause instanceof Error ? cause : new Error(String(cause));
}
