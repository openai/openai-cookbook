import { describe, expect, it, vi } from "vitest";
import {
  RealtimeSessionController,
  type RealtimeTransport,
  type SessionStatus,
} from "../src/mobile/session-controller.js";

class FakeTransport implements RealtimeTransport {
  closeCount = 0;
  private unexpectedClose: (error?: Error) => void = () => {};

  constructor(private readonly openResult: () => Promise<void>) {}

  open(): Promise<void> {
    return this.openResult();
  }

  close(): void {
    this.closeCount += 1;
  }

  setUnexpectedCloseHandler(handler: (error?: Error) => void): void {
    this.unexpectedClose = handler;
  }

  fail(): void {
    this.unexpectedClose(new Error("network changed"));
  }
}

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("RealtimeSessionController", () => {
  it("deduplicates concurrent starts", async () => {
    const opening = deferred();
    const transports: FakeTransport[] = [];
    const controller = new RealtimeSessionController({
      createTransport: () => {
        const transport = new FakeTransport(() => opening.promise);
        transports.push(transport);
        return transport;
      },
    });

    const first = controller.start();
    const second = controller.start();
    expect(transports).toHaveLength(1);
    opening.resolve();
    await Promise.all([first, second]);
    expect(controller.currentStatus).toBe("connected");
  });

  it("closes in the background and creates one fresh foreground session", async () => {
    const transports: FakeTransport[] = [];
    const controller = new RealtimeSessionController({
      createTransport: () => {
        const transport = new FakeTransport(async () => {});
        transports.push(transport);
        return transport;
      },
    });

    await controller.start();
    await controller.setAppActive(false);
    expect(controller.currentStatus).toBe("paused");
    expect(transports[0]?.closeCount).toBe(1);

    await controller.setAppActive(true);
    expect(transports).toHaveLength(2);
    expect(controller.currentStatus).toBe("connected");
  });

  it("does not resurrect a session stopped while opening", async () => {
    const opening = deferred();
    const transport = new FakeTransport(() => opening.promise);
    const controller = new RealtimeSessionController({
      createTransport: () => transport,
    });

    const start = controller.start();
    await controller.stop();
    opening.resolve();
    await start;
    expect(controller.currentStatus).toBe("idle");
    expect(transport.closeCount).toBeGreaterThanOrEqual(1);
  });

  it("uses bounded retries and then fails closed", async () => {
    vi.useFakeTimers();
    const statuses: SessionStatus[] = [];
    let attempts = 0;
    const controller = new RealtimeSessionController({
      createTransport: () =>
        new FakeTransport(async () => {
          attempts += 1;
          throw new Error("offline");
        }),
      retryDelaysMs: [10, 20],
      onStatus: (status) => statuses.push(status),
    });

    await controller.start();
    await vi.advanceTimersByTimeAsync(10);
    await vi.advanceTimersByTimeAsync(20);

    expect(attempts).toBe(3);
    expect(controller.currentStatus).toBe("failed");
    expect(statuses).toContain("reconnecting");
    vi.useRealTimers();
  });
});
