import {
  mediaDevices,
  MediaStream,
  MediaStreamTrack,
  RTCPeerConnection,
  RTCSessionDescription,
} from "react-native-webrtc";
import type {
  DataChannelLike,
  MediaStreamLike,
  MediaTrackLike,
  PeerConnectionLike,
  WebRtcBindings,
} from "./openai-webrtc-transport.js";

type NativeDataChannel = ReturnType<RTCPeerConnection["createDataChannel"]>;

export const reactNativeWebRtcBindings: WebRtcBindings = {
  createPeerConnection: () => wrapPeerConnection(new RTCPeerConnection()),
  createSessionDescription: (description) =>
    new RTCSessionDescription({
      type: description.type,
      sdp: description.sdp ?? "",
    }),
  getUserMedia: (constraints) => mediaDevices.getUserMedia(constraints),
};

function wrapPeerConnection(native: RTCPeerConnection): PeerConnectionLike {
  return {
    get connectionState() {
      return native.connectionState;
    },
    addTrack: (track: MediaTrackLike, stream: MediaStreamLike) => {
      native.addTrack(track as MediaStreamTrack, stream as MediaStream);
    },
    createDataChannel: (label: string) =>
      wrapDataChannel(native.createDataChannel(label)),
    createOffer: () => native.createOffer(),
    setLocalDescription: (description) =>
      native.setLocalDescription({
        type: description.type,
        sdp: description.sdp ?? "",
      }),
    setRemoteDescription: (description) =>
      native.setRemoteDescription(description as RTCSessionDescription),
    close: () => native.close(),
    setConnectionStateHandler: (handler) => {
      native.onconnectionstatechange = handler;
    },
    setTrackHandler: (handler) => {
      native.ontrack = handler
        ? (event: unknown) =>
            handler({
              streams: (event as unknown as { streams: MediaStream[] }).streams,
            })
        : null;
    },
  };
}

function wrapDataChannel(native: NativeDataChannel): DataChannelLike {
  return {
    get readyState() {
      return native.readyState;
    },
    send: (data) => native.send(data),
    close: () => native.close(),
    setOpenHandler: (handler) => {
      native.onopen = handler;
    },
    setCloseHandler: (handler) => {
      native.onclose = handler;
    },
    setErrorHandler: (handler) => {
      native.onerror = handler;
    },
    setMessageHandler: (handler) => {
      native.onmessage = handler
        ? (event: unknown) =>
            handler({
              data: (event as unknown as { data: unknown }).data,
            })
        : null;
    },
  };
}
