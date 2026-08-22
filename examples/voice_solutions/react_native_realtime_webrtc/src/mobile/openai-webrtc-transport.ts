import {
  parseRealtimeEvent,
  readTaskNoteRequest,
  type TaskNoteRequest,
} from "./realtime-events.js";
import type { RealtimeTransport } from "./session-controller.js";

type Description = { type: "offer" | "answer"; sdp?: string };

export interface MediaTrackLike {
  stop(): void;
}

export interface MediaStreamLike {
  getTracks(): MediaTrackLike[];
  getAudioTracks(): MediaTrackLike[];
}

export interface DataChannelLike {
  readyState: string;
  send(data: string): void;
  close(): void;
  setOpenHandler(handler: (() => void) | null): void;
  setCloseHandler(handler: (() => void) | null): void;
  setErrorHandler(handler: ((event: unknown) => void) | null): void;
  setMessageHandler(handler: ((event: { data: unknown }) => void) | null): void;
}

export interface PeerConnectionLike {
  connectionState: string;
  addTrack(track: MediaTrackLike, stream: MediaStreamLike): void;
  createDataChannel(label: string): DataChannelLike;
  createOffer(): Promise<Description>;
  setLocalDescription(description: Description): Promise<void>;
  setRemoteDescription(description: unknown): Promise<void>;
  close(): void;
  setConnectionStateHandler(handler: (() => void) | null): void;
  setTrackHandler(
    handler: ((event: { streams: MediaStreamLike[] }) => void) | null,
  ): void;
}

export type WebRtcBindings = {
  createPeerConnection: () => PeerConnectionLike;
  createSessionDescription: (description: Description) => unknown;
  getUserMedia: (constraints: {
    audio: boolean;
    video: boolean;
  }) => Promise<MediaStreamLike>;
};

export type ToolApprovalRequest = TaskNoteRequest & {
  respond: (output: Record<string, unknown>) => void;
};

export type OpenAIWebRtcTransportOptions = {
  backendSessionUrl: string;
  getBackendAccessToken: () => Promise<string>;
  demoUserId: string;
  webRtc: WebRtcBindings;
  fetchImpl?: typeof fetch;
  onRemoteStream?: (stream: MediaStreamLike) => void;
  onEvent?: (event: Record<string, unknown>) => void;
  onToolApprovalRequest?: (request: ToolApprovalRequest) => void;
  openTimeoutMs?: number;
};

export class OpenAIWebRtcTransport implements RealtimeTransport {
  private readonly options: OpenAIWebRtcTransportOptions;
  private readonly fetchImpl: typeof fetch;
  private peer: PeerConnectionLike | null = null;
  private channel: DataChannelLike | null = null;
  private localStream: MediaStreamLike | null = null;
  private unexpectedCloseHandler: (error?: Error) => void = () => {};
  private closing = false;
  private disconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private abortController: AbortController | null = null;

  constructor(options: OpenAIWebRtcTransportOptions) {
    this.options = options;
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  setUnexpectedCloseHandler(handler: (error?: Error) => void): void {
    this.unexpectedCloseHandler = handler;
  }

  async open(): Promise<void> {
    this.closing = false;
    this.abortController = new AbortController();
    const localStream = await this.options.webRtc.getUserMedia({
      audio: true,
      video: false,
    });
    if (this.closing) {
      for (const track of localStream.getTracks()) track.stop();
      throw new Error("Realtime connection was cancelled");
    }
    this.localStream = localStream;

    const accessToken = await this.options.getBackendAccessToken();
    const secretResponse = await this.fetchImpl(
      this.options.backendSessionUrl,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "X-Demo-User": this.options.demoUserId,
        },
        signal: this.abortController.signal,
      },
    );
    if (!secretResponse.ok) {
      throw new Error(`Session endpoint returned ${secretResponse.status}`);
    }

    const secretPayload = (await secretResponse.json()) as {
      client_secret?: unknown;
    };
    if (typeof secretPayload.client_secret !== "string") {
      throw new Error("Session endpoint did not return a client secret");
    }

    this.throwIfClosing();

    const peer = this.options.webRtc.createPeerConnection();
    this.peer = peer;
    const channel = peer.createDataChannel("oai-events");
    this.channel = channel;
    this.attachPeerHandlers(peer);
    this.attachChannelHandlers(channel);

    for (const track of localStream.getAudioTracks()) {
      peer.addTrack(track, localStream);
    }

    const offer = await peer.createOffer();
    this.throwIfClosing();
    await peer.setLocalDescription(offer);
    this.throwIfClosing();
    if (!offer.sdp) throw new Error("WebRTC offer did not contain SDP");

    const sdpResponse = await this.fetchImpl(
      "https://api.openai.com/v1/realtime/calls",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${secretPayload.client_secret}`,
          "Content-Type": "application/sdp",
        },
        body: offer.sdp,
        signal: this.abortController.signal,
      },
    );
    if (!sdpResponse.ok) {
      throw new Error(`Realtime call returned ${sdpResponse.status}`);
    }

    const answer = await sdpResponse.text();
    this.throwIfClosing();
    await peer.setRemoteDescription(
      this.options.webRtc.createSessionDescription({
        type: "answer",
        sdp: answer,
      }),
    );
    this.throwIfClosing();
    await waitForChannelOpen(
      channel,
      this.options.openTimeoutMs ?? 15_000,
      this.abortController.signal,
    );
  }

  close(): void {
    this.closing = true;
    this.abortController?.abort();
    this.abortController = null;
    this.clearDisconnectTimer();

    if (this.channel) {
      this.channel.setOpenHandler(null);
      this.channel.setCloseHandler(null);
      this.channel.setErrorHandler(null);
      this.channel.setMessageHandler(null);
      this.channel.close();
      this.channel = null;
    }

    if (this.peer) {
      this.peer.setConnectionStateHandler(null);
      this.peer.setTrackHandler(null);
      this.peer.close();
      this.peer = null;
    }

    for (const track of this.localStream?.getTracks() ?? []) track.stop();
    this.localStream = null;
  }

  private throwIfClosing(): void {
    if (this.closing || this.abortController?.signal.aborted) {
      throw new Error("Realtime connection was cancelled");
    }
  }

  private attachPeerHandlers(peer: PeerConnectionLike): void {
    peer.setTrackHandler(({ streams }) => {
      const remoteStream = streams[0];
      if (remoteStream) this.options.onRemoteStream?.(remoteStream);
    });

    peer.setConnectionStateHandler(() => {
      if (peer.connectionState === "connected") {
        this.clearDisconnectTimer();
      } else if (peer.connectionState === "failed") {
        this.notifyUnexpectedClose(new Error("WebRTC connection failed"));
      } else if (peer.connectionState === "disconnected") {
        this.clearDisconnectTimer();
        this.disconnectTimer = setTimeout(() => {
          if (peer.connectionState === "disconnected") {
            this.notifyUnexpectedClose(
              new Error("WebRTC connection remained disconnected"),
            );
          }
        }, 3_000);
      }
    });
  }

  private attachChannelHandlers(channel: DataChannelLike): void {
    channel.setMessageHandler(({ data }) => {
      const event = parseRealtimeEvent(data);
      if (!event) return;
      this.options.onEvent?.(event);

      const request = readTaskNoteRequest(event);
      if (!request) return;
      this.options.onToolApprovalRequest?.({
        ...request,
        respond: (output) => this.sendToolResult(request.callId, output),
      });
    });
    channel.setCloseHandler(() => {
      this.notifyUnexpectedClose(new Error("Realtime data channel closed"));
    });
    channel.setErrorHandler(() => {
      this.notifyUnexpectedClose(new Error("Realtime data channel failed"));
    });
  }

  private sendToolResult(
    callId: string,
    output: Record<string, unknown>,
  ): void {
    this.sendEvent({
      type: "conversation.item.create",
      item: {
        type: "function_call_output",
        call_id: callId,
        output: JSON.stringify(output),
      },
    });
    this.sendEvent({ type: "response.create" });
  }

  private sendEvent(event: Record<string, unknown>): void {
    if (!this.channel || this.channel.readyState !== "open") {
      throw new Error("Realtime data channel is not open");
    }
    this.channel.send(JSON.stringify(event));
  }

  private notifyUnexpectedClose(error: Error): void {
    if (!this.closing) this.unexpectedCloseHandler(error);
  }

  private clearDisconnectTimer(): void {
    if (this.disconnectTimer) {
      clearTimeout(this.disconnectTimer);
      this.disconnectTimer = null;
    }
  }
}

function waitForChannelOpen(
  channel: DataChannelLike,
  timeoutMs: number,
  signal: AbortSignal,
): Promise<void> {
  if (channel.readyState === "open") return Promise.resolve();

  return new Promise((resolve, reject) => {
    let timeout: ReturnType<typeof setTimeout> | null = null;
    const settle = (error?: Error) => {
      if (timeout) clearTimeout(timeout);
      timeout = null;
      signal.removeEventListener("abort", handleAbort);
      channel.setOpenHandler(null);
      if (error) reject(error);
      else resolve();
    };
    const handleAbort = () =>
      settle(new Error("Realtime connection was cancelled"));

    if (signal.aborted) {
      handleAbort();
      return;
    }

    signal.addEventListener("abort", handleAbort, { once: true });
    timeout = setTimeout(() => {
      settle(new Error("Timed out opening Realtime data channel"));
    }, timeoutMs);
    channel.setOpenHandler(() => {
      settle();
    });
  });
}
