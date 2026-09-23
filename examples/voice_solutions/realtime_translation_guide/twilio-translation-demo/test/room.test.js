import { describe, expect, it, vi } from "vitest";
import { TranslationRoom } from "../src/room.js";

const caller = (id, language) => ({
  callSid: id,
  language,
  languageLabel: language,
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
});
