import WebSocket from "ws";
import { describe, expect, it, vi } from "vitest";
import { TranslationRoom } from "../src/room.js";
import { buildApp } from "../src/server.js";

const caller = (id, language) => ({
  callSid: id,
  language,
  languageLabel: language,
  close: vi.fn(),
  sendTwilioMedia: vi.fn(),
});

describe("TranslationRoom", () => {
  it("waits for a second caller before pairing", () => {
    const room = new TranslationRoom({ createBridge: vi.fn() });
    room.addCaller(caller("CA1", "en"));
    expect(room.status().waiting).toBe(1);
    expect(room.status().activePairs).toBe(0);
  });

  it("creates one translation bridge per direction using the listener language", () => {
    const createBridge = vi.fn(() => ({ close: vi.fn() }));
    const room = new TranslationRoom({ createBridge });
    room.addCaller(caller("CA1", "en"));
    room.addCaller(caller("CA2", "es"));

    expect(room.status().waiting).toBe(0);
    expect(room.status().activePairs).toBe(1);
    expect(createBridge).toHaveBeenCalledTimes(2);
    expect(createBridge.mock.calls[0][0]).toMatchObject({
      sourceLabel: "CA1",
      targetLanguage: "es",
    });
    expect(createBridge.mock.calls[1][0]).toMatchObject({
      sourceLabel: "CA2",
      targetLanguage: "en",
    });
  });

  it("replaces a waiting caller with the same callSid instead of pairing a stale entry", () => {
    const createBridge = vi.fn(() => ({
      close: vi.fn(),
      sendTwilioMedia: vi.fn(),
    }));
    const room = new TranslationRoom({ createBridge });
    const staleCaller = caller("CA1", "en");
    const replacementCaller = caller("CA1", "fr");
    const secondCaller = caller("CA2", "es");

    room.addCaller(staleCaller);
    room.addCaller(replacementCaller);

    expect(staleCaller.close).toHaveBeenCalledTimes(1);
    expect(room.status()).toEqual({
      activeCallers: 1,
      activePairs: 0,
      waiting: 1,
    });

    room.addCaller(secondCaller);
    room.handleMedia("CA1", "audio-chunk");

    expect(createBridge.mock.calls[1][0].target).toBe(replacementCaller);
    expect(createBridge.mock.calls[1][0].targetLanguage).toBe("fr");
    expect(replacementCaller.bridgeToPeer.sendTwilioMedia).toHaveBeenCalledWith(
      "audio-chunk",
    );
  });

  it("tears down an active pair and its bridges when a paired callSid reconnects", () => {
    const bridges = [];
    const createBridge = vi.fn(() => {
      const bridge = { close: vi.fn(), sendTwilioMedia: vi.fn() };
      bridges.push(bridge);
      return bridge;
    });
    const room = new TranslationRoom({ createBridge });
    const firstCaller = caller("CA1", "en");
    const peerCaller = caller("CA2", "es");
    const reconnectedCaller = caller("CA1", "en");

    room.addCaller(firstCaller);
    room.addCaller(peerCaller);
    room.addCaller(reconnectedCaller);

    expect(bridges[0].close).toHaveBeenCalledTimes(1);
    expect(bridges[1].close).toHaveBeenCalledTimes(1);
    expect(firstCaller.close).toHaveBeenCalledTimes(1);
    expect(peerCaller.close).toHaveBeenCalledTimes(1);
    expect(room.status()).toEqual({
      activeCallers: 1,
      activePairs: 0,
      waiting: 1,
    });

    room.removeCaller("CA1", firstCaller);
    room.removeCaller("CA2", peerCaller);
    expect(room.status()).toEqual({
      activeCallers: 1,
      activePairs: 0,
      waiting: 1,
    });
  });

  it("closes an already-created bridge and clears callers if bridge setup fails", () => {
    const firstBridge = { close: vi.fn() };
    const createBridge = vi
      .fn()
      .mockReturnValueOnce(firstBridge)
      .mockImplementationOnce(() => {
        throw new Error("bridge setup failed");
      });
    const room = new TranslationRoom({ createBridge });
    const firstCaller = caller("CA1", "en");
    const secondCaller = caller("CA2", "es");

    room.addCaller(firstCaller);
    expect(() => room.addCaller(secondCaller)).toThrow("bridge setup failed");

    expect(firstBridge.close).toHaveBeenCalledTimes(1);
    expect(firstCaller.close).toHaveBeenCalledTimes(1);
    expect(secondCaller.close).toHaveBeenCalledTimes(1);
    expect(room.status()).toEqual({
      activeCallers: 0,
      activePairs: 0,
      waiting: 0,
    });
  });

  it("keeps a replacement media-stream caller active when the superseded socket closes", async () => {
    const logger = { info: vi.fn(), warn: vi.fn(), error: vi.fn() };
    const app = buildApp(
      { SKIP_TWILIO_SIGNATURE_VALIDATION: "true" },
      logger,
    );
    const address = await app.listen({ host: "127.0.0.1", port: 0 });
    const wsUrl = address.replace(/^http/, "ws") + "/media-stream";

    try {
      const firstSocket = new WebSocket(wsUrl);
      await new Promise((resolve) => firstSocket.once("open", resolve));
      firstSocket.send(
        JSON.stringify({
          event: "start",
          start: {
            streamSid: "MZ1",
            customParameters: { callSid: "CA1", language: "en" },
          },
        }),
      );
      await vi.waitFor(async () => {
        const res = await app.inject({ method: "GET", url: "/status" });
        expect(res.json()).toEqual({
          activeCallers: 1,
          activePairs: 0,
          waiting: 1,
        });
      });

      const secondSocket = new WebSocket(wsUrl);
      await new Promise((resolve) => secondSocket.once("open", resolve));
      const firstClosed = new Promise((resolve) =>
        firstSocket.once("close", resolve),
      );
      secondSocket.send(
        JSON.stringify({
          event: "start",
          start: {
            streamSid: "MZ2",
            customParameters: { callSid: "CA1", language: "es" },
          },
        }),
      );
      await firstClosed;

      const statusAfterSupersede = await app.inject({
        method: "GET",
        url: "/status",
      });
      expect(statusAfterSupersede.json()).toEqual({
        activeCallers: 1,
        activePairs: 0,
        waiting: 1,
      });

      const secondClosed = new Promise((resolve) =>
        secondSocket.once("close", resolve),
      );
      secondSocket.close();
      await secondClosed;
    } finally {
      await app.close();
    }
  });
});
