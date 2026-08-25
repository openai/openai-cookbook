import { describe, expect, it, vi } from "vitest";
import {
  OpenAIWebRtcTransport,
  type DataChannelLike,
  type MediaStreamLike,
  type PeerConnectionLike,
  type WebRtcBindings,
} from "../src/mobile/openai-webrtc-transport.js";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function createMediaStream() {
  const track = { stop: vi.fn() };
  const stream: MediaStreamLike = {
    getTracks: () => [track],
    getAudioTracks: () => [track],
  };
  return { stream, track };
}

function createPeer() {
  let openHandler: (() => void) | null | undefined;
  const channel: DataChannelLike = {
    readyState: "connecting",
    send: vi.fn(),
    close: vi.fn(),
    setOpenHandler: vi.fn((handler) => {
      openHandler = handler;
    }),
    setCloseHandler: vi.fn(),
    setErrorHandler: vi.fn(),
    setMessageHandler: vi.fn(),
  };
  const peer: PeerConnectionLike = {
    connectionState: "new",
    addTrack: vi.fn(),
    createDataChannel: vi.fn(() => channel),
    createOffer: vi.fn(async () => ({
      type: "offer" as const,
      sdp: "offer-sdp",
    })),
    setLocalDescription: vi.fn(async () => {}),
    setRemoteDescription: vi.fn(async () => {}),
    close: vi.fn(),
    setConnectionStateHandler: vi.fn(),
    setTrackHandler: vi.fn(),
  };
  return { peer, channel, getOpenHandler: () => openHandler };
}

async function waitUntil(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (predicate()) return;
    await Promise.resolve();
  }
  throw new Error("Condition was not reached");
}

describe("OpenAIWebRtcTransport", () => {
  it("does not allocate native resources after close begins", async () => {
    const secretPayload = deferred<{ client_secret: string }>();
    const { stream, track } = createMediaStream();
    const createPeerConnection = vi.fn<() => PeerConnectionLike>();
    const webRtc: WebRtcBindings = {
      createPeerConnection,
      createSessionDescription: (description) => description,
      getUserMedia: async () => stream,
    };
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      ({
        ok: true,
        status: 200,
        json: () => secretPayload.promise,
      }) as Response,
    );
    const transport = new OpenAIWebRtcTransport({
      backendSessionUrl: "https://demo.invalid/session",
      getBackendAccessToken: async () => "demo-token",
      demoUserId: "user_123",
      webRtc,
      fetchImpl,
    });

    const opening = transport.open();
    await waitUntil(() => fetchImpl.mock.calls.length === 1);
    transport.close();
    secretPayload.resolve({ client_secret: "ek_test" });

    await expect(opening).rejects.toThrow("cancelled");
    expect(createPeerConnection).not.toHaveBeenCalled();
    expect(track.stop).toHaveBeenCalledOnce();
  });

  it("rejects the data-channel wait immediately during teardown", async () => {
    const { stream } = createMediaStream();
    const { peer, channel, getOpenHandler } = createPeer();
    const webRtc: WebRtcBindings = {
      createPeerConnection: () => peer,
      createSessionDescription: (description) => description,
      getUserMedia: async () => stream,
    };
    const fetchImpl = vi.fn<typeof fetch>(async (input) =>
      String(input).includes("/realtime/calls")
        ? new Response("answer-sdp", { status: 200 })
        : Response.json({ client_secret: "ek_test" }),
    );
    const transport = new OpenAIWebRtcTransport({
      backendSessionUrl: "https://demo.invalid/session",
      getBackendAccessToken: async () => "demo-token",
      demoUserId: "user_123",
      webRtc,
      fetchImpl,
      openTimeoutMs: 60_000,
    });

    const opening = transport.open();
    await waitUntil(() => typeof getOpenHandler() === "function");
    transport.close();

    await expect(opening).rejects.toThrow("cancelled");
    expect(channel.close).toHaveBeenCalledOnce();
    expect(peer.close).toHaveBeenCalledOnce();
  });
});
