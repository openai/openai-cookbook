"use client"

import * as React from "react"

import {
  REALTIME_TRANSLATION_CALL_URL,
  TRANSLATION_LANGUAGES,
  buildSessionUpdate,
} from "@/lib/realtime-translation-config"

export type TranslationLanguage = {
  value: string
  label: string
}

export { TRANSLATION_LANGUAGES }

export type TranslationStatus = "idle" | "connecting" | "connected" | "error"

type TranslationTokenResponse = {
  clientSecret: string
  expiresAt: number | null
}

type UseRemoteTranslationOptions = {
  enabled: boolean
  sourceTrack: MediaStreamTrack | null
  language: string
  sourceTranscriptionEnabled: boolean
  noiseReductionEnabled: boolean
  translatedVolume: number
}

export type UseRemoteTranslationResult = {
  status: TranslationStatus
  error: string | null
  sourceTranscript: string
  translatedTranscript: string
  sourceSubtitle: string
  translatedSubtitle: string
  hasOutputAudio: boolean
}

type TranslationSessionConfig = {
  language: string
  sourceTranscriptionEnabled: boolean
  noiseReductionEnabled: boolean
}

type RealtimeEvent = {
  type?: unknown
  delta?: unknown
  error?: unknown
}

export function useRemoteTranslation({
  enabled,
  sourceTrack,
  language,
  sourceTranscriptionEnabled,
  noiseReductionEnabled,
  translatedVolume,
}: UseRemoteTranslationOptions): UseRemoteTranslationResult {
  const [status, setStatus] = React.useState<TranslationStatus>("idle")
  const [error, setError] = React.useState<string | null>(null)
  const [sourceTranscript, setSourceTranscript] = React.useState("")
  const [translatedTranscript, setTranslatedTranscript] = React.useState("")
  const [hasOutputAudio, setHasOutputAudio] = React.useState(false)
  const peerConnectionRef = React.useRef<RTCPeerConnection | null>(null)
  const dataChannelRef = React.useRef<RTCDataChannel | null>(null)
  const translatedAudioRef = React.useRef<HTMLAudioElement | null>(null)
  const translatedVolumeRef = React.useRef(translatedVolume)
  const sessionConfigRef = React.useRef<TranslationSessionConfig>({
    language,
    sourceTranscriptionEnabled,
    noiseReductionEnabled,
  })
  const active = enabled && !!sourceTrack

  React.useEffect(() => {
    translatedVolumeRef.current = translatedVolume
    if (translatedAudioRef.current) {
      translatedAudioRef.current.volume = translatedVolume
    }
  }, [translatedVolume])

  React.useEffect(() => {
    const nextConfig = {
      language,
      sourceTranscriptionEnabled,
      noiseReductionEnabled,
    }
    sessionConfigRef.current = nextConfig

    const dataChannel = dataChannelRef.current
    if (!active || !dataChannel || dataChannel.readyState !== "open") {
      return
    }

    dataChannel.send(JSON.stringify(buildTranslationSessionUpdate(nextConfig)))
  }, [active, language, noiseReductionEnabled, sourceTranscriptionEnabled])

  React.useEffect(() => {
    if (!active || !sourceTrack) {
      return
    }

    const activeSourceTrack = sourceTrack
    let cancelled = false
    let peerConnection: RTCPeerConnection | null = null
    let dataChannel: RTCDataChannel | null = null
    let translatedAudio: HTMLAudioElement | null = null

    async function connect() {
      const initialSessionConfig = sessionConfigRef.current
      setStatus("connecting")
      setError(null)
      setSourceTranscript("")
      setTranslatedTranscript("")
      setHasOutputAudio(false)

      try {
        const tokenResponse = await fetch("/api/realtime/translation-token", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            language: initialSessionConfig.language,
            inputTranscriptionEnabled:
              initialSessionConfig.sourceTranscriptionEnabled,
            noiseReductionEnabled: initialSessionConfig.noiseReductionEnabled,
          }),
        })

        if (!tokenResponse.ok) {
          throw new Error(await tokenResponse.text())
        }

        const token = (await tokenResponse.json()) as TranslationTokenResponse

        if (cancelled) {
          return
        }

        peerConnection = new RTCPeerConnection()
        dataChannel = peerConnection.createDataChannel("oai-events")
        translatedAudio = new Audio()
        translatedAudio.autoplay = true
        translatedAudio.setAttribute("playsinline", "")
        translatedAudio.volume = translatedVolumeRef.current

        peerConnectionRef.current = peerConnection
        dataChannelRef.current = dataChannel
        translatedAudioRef.current = translatedAudio

        peerConnection.ontrack = ({ streams, track }) => {
          if (!translatedAudio) {
            return
          }

          translatedAudio.srcObject = streams[0] ?? new MediaStream([track])
          setHasOutputAudio(true)
          void translatedAudio.play().catch((audioError) => {
            setError(getErrorMessage(audioError))
          })
        }

        peerConnection.onconnectionstatechange = () => {
          if (!peerConnection || cancelled) {
            return
          }

          if (peerConnection.connectionState === "failed") {
            setError("Translation WebRTC connection failed")
            setStatus("error")
          }

          if (peerConnection.connectionState === "connected") {
            setStatus("connected")
          }
        }

        dataChannel.onopen = () => {
          if (!dataChannel || cancelled) {
            return
          }

          dataChannel.send(
            JSON.stringify(
              buildTranslationSessionUpdate(sessionConfigRef.current)
            )
          )
        }
        dataChannel.onmessage = (event) => {
          if (!cancelled) {
            void handleRealtimeEvent(event.data, {
              onSessionReady: () => setStatus("connected"),
              onInputTranscript: (delta) => {
                setSourceTranscript((current) =>
                  appendTranscriptDelta(current, delta)
                )
              },
              onOutputAudio: () => setHasOutputAudio(true),
              onOutputTranscript: (delta) => {
                setTranslatedTranscript((current) =>
                  appendTranscriptDelta(current, delta)
                )
              },
              onError: (message) => {
                setError(message)
                setStatus("error")
              },
            })
          }
        }
        dataChannel.onerror = () => {
          if (!cancelled) {
            setError("Translation data channel failed")
            setStatus("error")
          }
        }

        peerConnection.addTrack(
          activeSourceTrack,
          new MediaStream([activeSourceTrack])
        )

        const offer = await peerConnection.createOffer()
        await peerConnection.setLocalDescription(offer)

        const sdpResponse = await fetch(REALTIME_TRANSLATION_CALL_URL, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token.clientSecret}`,
            "Content-Type": "application/sdp",
          },
          body: offer.sdp,
        })

        const answerSdp = await sdpResponse.text()
        if (!sdpResponse.ok) {
          throw new Error(answerSdp)
        }

        await peerConnection.setRemoteDescription({
          type: "answer",
          sdp: answerSdp,
        })

        if (!cancelled) {
          setStatus("connected")
        }
      } catch (connectError) {
        if (!cancelled) {
          setError(getErrorMessage(connectError))
          setStatus("error")
        }
      }
    }

    void connect()

    return () => {
      cancelled = true
      dataChannel?.close()
      peerConnection?.close()

      if (translatedAudio) {
        translatedAudio.pause()
        translatedAudio.srcObject = null
      }

      if (dataChannelRef.current === dataChannel) {
        dataChannelRef.current = null
      }
      if (peerConnectionRef.current === peerConnection) {
        peerConnectionRef.current = null
      }
      if (translatedAudioRef.current === translatedAudio) {
        translatedAudioRef.current = null
      }
    }
  }, [active, sourceTrack])

  return {
    status: active ? status : "idle",
    error: active ? error : null,
    sourceTranscript,
    translatedTranscript,
    sourceSubtitle: getSubtitle(sourceTranscript),
    translatedSubtitle: getSubtitle(translatedTranscript),
    hasOutputAudio: active ? hasOutputAudio : false,
  }
}

async function handleRealtimeEvent(
  payload: unknown,
  handlers: {
    onSessionReady: () => void
    onInputTranscript: (delta: string) => void
    onOutputAudio: () => void
    onOutputTranscript: (delta: string) => void
    onError: (message: string) => void
  }
) {
  const text =
    typeof payload === "string"
      ? payload
      : payload instanceof Blob
        ? await payload.text()
        : null

  if (!text) {
    return
  }

  let event: RealtimeEvent
  try {
    event = JSON.parse(text) as RealtimeEvent
  } catch {
    return
  }

  if (event.type === "session.updated") {
    handlers.onSessionReady()
    return
  }

  if (event.type === "session.input_transcript.delta") {
    if (typeof event.delta === "string") {
      handlers.onInputTranscript(event.delta)
    }
    return
  }

  if (event.type === "session.output_audio.delta") {
    handlers.onOutputAudio()
    return
  }

  if (event.type === "session.output_transcript.delta") {
    if (typeof event.delta === "string") {
      handlers.onOutputTranscript(event.delta)
    }
    return
  }

  if (event.type === "error") {
    const error = event.error
    if (error && typeof error === "object" && !Array.isArray(error)) {
      const message = (error as Record<string, unknown>).message
      handlers.onError(
        typeof message === "string" ? message : "Translation error"
      )
      return
    }

    handlers.onError("Translation error")
  }
}

function appendTranscriptDelta(current: string, delta: string) {
  if (!delta) {
    return current
  }

  if (!current) {
    return delta.replace(/^\s+/, "")
  }

  if (
    /\s$/.test(current) ||
    /^\s/.test(delta) ||
    /^[,.;:!?%)}\]]/.test(delta)
  ) {
    return `${current}${delta}`
  }

  return `${current} ${delta}`
}

function buildTranslationSessionUpdate(config: TranslationSessionConfig) {
  return buildSessionUpdate({
    language: config.language,
    inputTranscriptionEnabled: config.sourceTranscriptionEnabled,
    noiseReductionEnabled: config.noiseReductionEnabled,
  })
}

function getSubtitle(transcript: string) {
  const normalized = transcript.replace(/\s+/g, " ").trim()

  if (!normalized) {
    return ""
  }

  const sentenceStart = Math.max(
    normalized.lastIndexOf(". "),
    normalized.lastIndexOf("? "),
    normalized.lastIndexOf("! ")
  )
  const latest =
    sentenceStart >= 0 ? normalized.slice(sentenceStart + 2) : normalized

  return latest.length > 180 ? latest.slice(latest.length - 180) : latest
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Translation failed"
}
