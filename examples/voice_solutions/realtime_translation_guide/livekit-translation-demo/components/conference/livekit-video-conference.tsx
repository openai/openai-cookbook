"use client"

import * as React from "react"
import Image from "next/image"
import {
  Room,
  RoomEvent,
  Track,
  VideoPresets,
  type Participant,
  type RoomConnectOptions,
} from "livekit-client"
import {
  AlertCircleIcon,
  CheckIcon,
  ChevronDownIcon,
  CopyIcon,
  LanguagesIcon,
  PhoneOffIcon,
  VideoOffIcon,
} from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Separator } from "@/components/ui/separator"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Spinner } from "@/components/ui/spinner"
import { Switch } from "@/components/ui/switch"
import { useMounted } from "@/hooks/use-mounted"
import { cn } from "@/lib/utils"
import {
  TRANSLATION_LANGUAGES,
  useRemoteTranslation,
  type TranslationStatus,
  type UseRemoteTranslationResult,
} from "@/lib/realtime-translation"

type ConnectionDetails = {
  serverUrl: string
  roomName: string
  participantName: string
  participantToken: string
}

type JoinState = "setup" | "connecting" | "connected"
type MediaPermissionName = "camera" | "microphone"
type MeetingTileModel = {
  participant: Participant
  label: string
  isLocal: boolean
  highlighted: boolean
  visualIndex: number
}
type ParticipantPresence = {
  identity: string
  name: string
}
type ParticipantsResponse = {
  participants: ParticipantPresence[]
}
type DeviceMenuKind = "audio" | "video"
type DeviceMenuOption = {
  id: string
  label: string
  selected: boolean
  disabled?: boolean
  onSelect: () => void
}
type DeviceMenuSection = {
  label: string
  emptyLabel: string
  options: DeviceMenuOption[]
}
type ParticipantTranslationSnapshot = UseRemoteTranslationResult & {
  participantId: string
  participantName: string
  hasSourceTrack: boolean
}

const DEFAULT_ROOM_NAME = "test-demo"
const DEFAULT_PARTICIPANT_NAME = "Blossom"
const MAX_VISIBLE_PARTICIPANTS = 6
const SPEAKING_LEVEL_FLOOR = 0.08
const LANDSCAPE_VIDEO = VideoPresets.h1080
const LANDSCAPE_VIDEO_CONSTRAINTS = {
  aspectRatio: { ideal: 16 / 9 },
  frameRate: { ideal: 30, max: 30 },
  height: { ideal: LANDSCAPE_VIDEO.height },
  width: { ideal: LANDSCAPE_VIDEO.width },
} satisfies MediaTrackConstraints

const CONNECT_OPTIONS: RoomConnectOptions = {
  autoSubscribe: true,
}

function getDeviceLabel(
  device: MediaDeviceInfo,
  fallbackPrefix: "Camera" | "Microphone" | "Speaker",
  index: number
) {
  const label = device.label.trim() || `${fallbackPrefix} ${index + 1}`
  return label.replace(/\s+\([0-9a-f]{4}:[0-9a-f]{4}\)$/i, "")
}

export function LiveKitVideoConference({
  initialRoomName,
}: {
  initialRoomName?: string
}) {
  const [participantName, setParticipantName] = React.useState(
    DEFAULT_PARTICIPANT_NAME
  )
  const [roomName, setRoomName] = React.useState(
    initialRoomName?.trim() || DEFAULT_ROOM_NAME
  )
  const [translationLanguage, setTranslationLanguage] = React.useState("es")
  const [audioInputs, setAudioInputs] = React.useState<MediaDeviceInfo[]>([])
  const [audioOutputs, setAudioOutputs] = React.useState<MediaDeviceInfo[]>([])
  const [videoInputs, setVideoInputs] = React.useState<MediaDeviceInfo[]>([])
  const [audioDeviceId, setAudioDeviceId] = React.useState("")
  const [audioOutputDeviceId, setAudioOutputDeviceId] = React.useState("")
  const [videoDeviceId, setVideoDeviceId] = React.useState("")
  const [micEnabled, setMicEnabled] = React.useState(true)
  const [cameraEnabled, setCameraEnabled] = React.useState(true)
  const [previewStream, setPreviewStream] = React.useState<MediaStream | null>(
    null
  )
  const [joinState, setJoinState] = React.useState<JoinState>("setup")
  const [room, setRoom] = React.useState<Room | null>(null)
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)
  const [previewErrorMessage, setPreviewErrorMessage] = React.useState<
    string | null
  >(null)
  const [previewRequestKey, setPreviewRequestKey] = React.useState(0)
  const [permissionRevision, setPermissionRevision] = React.useState(0)
  const [, setRevision] = React.useState(0)
  const [lobbyParticipants, setLobbyParticipants] = React.useState<
    ParticipantPresence[]
  >([])
  const hasMounted = useMounted()

  const previewVideoRef = React.useRef<HTMLVideoElement | null>(null)

  React.useEffect(() => {
    let cancelled = false
    const statuses: PermissionStatus[] = []

    async function watchMediaPermissions() {
      const nextStatuses = await Promise.all([
        queryMediaPermission("camera"),
        queryMediaPermission("microphone"),
      ])

      if (cancelled) {
        return
      }

      nextStatuses.forEach((status) => {
        if (!status) {
          return
        }

        statuses.push(status)
        status.onchange = () => {
          setPermissionRevision((current) => current + 1)
        }
      })
    }

    watchMediaPermissions()

    return () => {
      cancelled = true
      statuses.forEach((status) => {
        status.onchange = null
      })
    }
  }, [])

  React.useEffect(() => {
    if (joinState !== "setup") {
      return
    }

    const normalizedRoomName = roomName.trim() || DEFAULT_ROOM_NAME
    let cancelled = false
    let activeController: AbortController | null = null

    async function refreshParticipants() {
      activeController?.abort()
      const controller = new AbortController()
      activeController = controller

      try {
        const participantsUrl = new URL(
          "/api/livekit/participants",
          window.location.origin
        )
        participantsUrl.searchParams.set("roomName", normalizedRoomName)

        const response = await fetch(participantsUrl.toString(), {
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new Error(await response.text())
        }

        const data = (await response.json()) as ParticipantsResponse

        if (!cancelled) {
          setLobbyParticipants(data.participants)
        }
      } catch {
        if (!cancelled && !controller.signal.aborted) {
          setLobbyParticipants([])
        }
      }
    }

    void refreshParticipants()
    const interval = window.setInterval(() => {
      void refreshParticipants()
    }, 3000)

    return () => {
      cancelled = true
      activeController?.abort()
      window.clearInterval(interval)
    }
  }, [joinState, roomName])

  const applyDevices = React.useCallback((devices: MediaDeviceInfo[]) => {
    const nextAudioInputs = devices.filter(
      (device) => device.kind === "audioinput" && device.deviceId
    )
    const nextAudioOutputs = devices.filter(
      (device) => device.kind === "audiooutput" && device.deviceId
    )
    const nextVideoInputs = devices.filter(
      (device) => device.kind === "videoinput" && device.deviceId
    )

    setAudioInputs(nextAudioInputs)
    setAudioOutputs(nextAudioOutputs)
    setVideoInputs(nextVideoInputs)
    setAudioDeviceId((current) =>
      nextAudioInputs.some((device) => device.deviceId === current)
        ? current
        : nextAudioInputs[0]?.deviceId || ""
    )
    setAudioOutputDeviceId((current) =>
      nextAudioOutputs.some((device) => device.deviceId === current)
        ? current
        : nextAudioOutputs.find((device) => device.deviceId === "default")
            ?.deviceId ||
          nextAudioOutputs[0]?.deviceId ||
          ""
    )
    setVideoDeviceId((current) =>
      nextVideoInputs.some((device) => device.deviceId === current)
        ? current
        : nextVideoInputs[0]?.deviceId || ""
    )
  }, [])

  const refreshDevices = React.useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) {
      return
    }

    applyDevices(await navigator.mediaDevices.enumerateDevices())
  }, [applyDevices])

  React.useEffect(() => {
    if (!navigator.mediaDevices?.enumerateDevices) {
      return
    }

    let cancelled = false

    function loadDevices() {
      navigator.mediaDevices
        .enumerateDevices()
        .then((devices) => {
          if (!cancelled) {
            applyDevices(devices)
          }
        })
        .catch((error) => {
          console.error(error)
        })
    }

    loadDevices()
    navigator.mediaDevices.addEventListener("devicechange", loadDevices)

    return () => {
      cancelled = true
      navigator.mediaDevices.removeEventListener("devicechange", loadDevices)
    }
  }, [applyDevices])

  React.useEffect(() => {
    if (joinState !== "setup") {
      return
    }

    if (!cameraEnabled && !micEnabled) {
      return
    }

    let cancelled = false
    let stream: MediaStream | null = null

    async function startPreview() {
      try {
        const [cameraPermission, microphonePermission] = await Promise.all([
          cameraEnabled ? queryMediaPermission("camera") : null,
          micEnabled ? queryMediaPermission("microphone") : null,
        ])

        if (cancelled) {
          return
        }

        if (
          cameraPermission?.state === "denied" ||
          microphonePermission?.state === "denied"
        ) {
          setPreviewStream((current) => {
            stopMediaStream(current)
            return null
          })
          setPreviewErrorMessage("Camera blocked")
          return
        }

        stream = await navigator.mediaDevices.getUserMedia({
          video: cameraEnabled
            ? {
                deviceId: videoDeviceId ? { exact: videoDeviceId } : undefined,
                ...LANDSCAPE_VIDEO_CONSTRAINTS,
              }
            : false,
          audio: micEnabled
            ? { deviceId: audioDeviceId ? { exact: audioDeviceId } : undefined }
            : false,
        })

        if (cancelled) {
          stopMediaStream(stream)
          return
        }

        setPreviewStream((current) => {
          stopMediaStream(current)
          return stream
        })

        await refreshDevices()
        setPreviewErrorMessage(null)
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "Unable to open the selected camera or microphone."
        setPreviewErrorMessage(message)
      }
    }

    startPreview()

    return () => {
      cancelled = true
      stopMediaStream(stream)
    }
  }, [
    audioDeviceId,
    cameraEnabled,
    joinState,
    micEnabled,
    permissionRevision,
    previewRequestKey,
    refreshDevices,
    videoDeviceId,
  ])

  React.useEffect(() => {
    const previewVideo = previewVideoRef.current

    if (!previewVideo) {
      return
    }

    previewVideo.srcObject = previewStream

    return () => {
      previewVideo.srcObject = null
    }
  }, [previewStream])

  React.useEffect(() => {
    return () => {
      room?.disconnect()
      stopMediaStream(previewStream)
    }
  }, [previewStream, room])

  const roomUrl = React.useMemo(() => {
    if (typeof window === "undefined") {
      return ""
    }

    const url = new URL(window.location.href)
    url.pathname = `/${encodeURIComponent(roomName.trim() || DEFAULT_ROOM_NAME)}`
    url.search = ""
    url.hash = ""
    return url.toString()
  }, [roomName])

  const participants = room
    ? [room.localParticipant, ...Array.from(room.remoteParticipants.values())]
    : []
  const isConnected = joinState === "connected" && room

  React.useEffect(() => {
    document.body.dataset.meetingState = isConnected ? "connected" : "lobby"
    window.dispatchEvent(
      new CustomEvent("realtime-translation:meeting-state")
    )

    return () => {
      document.body.dataset.meetingState = "lobby"
      window.dispatchEvent(
        new CustomEvent("realtime-translation:meeting-state")
      )
    }
  }, [isConnected])

  async function joinRoom(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const normalizedRoomName = roomName.trim() || DEFAULT_ROOM_NAME
    const normalizedParticipantName =
      participantName.trim() || DEFAULT_PARTICIPANT_NAME
    let nextRoom: Room | null = null

    window.history.replaceState(
      null,
      "",
      `/${encodeURIComponent(normalizedRoomName)}`
    )
    setJoinState("connecting")
    setErrorMessage(null)

    try {
      const tokenUrl = new URL("/api/livekit/token", window.location.origin)
      tokenUrl.searchParams.set("roomName", normalizedRoomName)
      tokenUrl.searchParams.set("participantName", normalizedParticipantName)

      const response = await fetch(tokenUrl.toString())
      if (!response.ok) {
        throw new Error(await response.text())
      }

      const details = (await response.json()) as ConnectionDetails
      nextRoom = new Room({
        adaptiveStream: true,
        dynacast: true,
        videoCaptureDefaults: {
          deviceId: videoDeviceId || undefined,
          frameRate: 30,
          resolution: LANDSCAPE_VIDEO,
        },
        audioCaptureDefaults: {
          deviceId: audioDeviceId || undefined,
        },
        publishDefaults: {
          red: true,
          simulcast: false,
          videoEncoding: LANDSCAPE_VIDEO.encoding,
        },
      })

      const bumpRevision = () => setRevision((current) => current + 1)
      nextRoom
        .on(RoomEvent.Connected, bumpRevision)
        .on(RoomEvent.ConnectionStateChanged, bumpRevision)
        .on(RoomEvent.ParticipantConnected, bumpRevision)
        .on(RoomEvent.ParticipantDisconnected, bumpRevision)
        .on(RoomEvent.TrackSubscribed, bumpRevision)
        .on(RoomEvent.TrackUnsubscribed, bumpRevision)
        .on(RoomEvent.TrackPublished, bumpRevision)
        .on(RoomEvent.TrackUnpublished, bumpRevision)
        .on(RoomEvent.TrackMuted, bumpRevision)
        .on(RoomEvent.TrackUnmuted, bumpRevision)
        .on(RoomEvent.LocalTrackPublished, bumpRevision)
        .on(RoomEvent.LocalTrackUnpublished, bumpRevision)
        .on(RoomEvent.Disconnected, bumpRevision)

      setPreviewStream((current) => {
        stopMediaStream(current)
        return null
      })
      setRoom(nextRoom)

      await nextRoom.connect(
        details.serverUrl,
        details.participantToken,
        CONNECT_OPTIONS
      )

      if (cameraEnabled) {
        await nextRoom.localParticipant.setCameraEnabled(true, {
          deviceId: videoDeviceId || undefined,
          frameRate: 30,
          resolution: LANDSCAPE_VIDEO,
        })
      }

      if (micEnabled) {
        await nextRoom.localParticipant.setMicrophoneEnabled(true, {
          deviceId: audioDeviceId || undefined,
        })
      }

      setJoinState("connected")
      bumpRevision()
    } catch (error) {
      nextRoom?.disconnect()
      room?.disconnect()
      const message =
        error instanceof Error ? error.message : "Unable to join the room."
      setErrorMessage(message)
      setJoinState("setup")
      setRoom(null)
    }
  }

  async function leaveRoom() {
    room?.disconnect()
    setRoom(null)
    setJoinState("setup")
    setRevision((current) => current + 1)
    await refreshDevices()
  }

  async function copyRoomUrl() {
    await copyTextToClipboard(roomUrl)
  }

  async function toggleMicrophone() {
    const nextEnabled = !micEnabled
    setMicEnabled(nextEnabled)
    if (!nextEnabled && !cameraEnabled) {
      setPreviewStream((current) => {
        stopMediaStream(current)
        return null
      })
    }

    if (room) {
      await room.localParticipant.setMicrophoneEnabled(nextEnabled, {
        deviceId: audioDeviceId || undefined,
      })
    }
  }

  async function toggleCamera() {
    const nextEnabled = !cameraEnabled
    setCameraEnabled(nextEnabled)
    if (!nextEnabled && !micEnabled) {
      setPreviewStream((current) => {
        stopMediaStream(current)
        return null
      })
    }

    if (room) {
      await room.localParticipant.setCameraEnabled(nextEnabled, {
        deviceId: videoDeviceId || undefined,
        frameRate: 30,
        resolution: LANDSCAPE_VIDEO,
      })
    }
  }

  async function selectAudioDevice(deviceId: string) {
    setAudioDeviceId(deviceId)

    if (room && micEnabled) {
      await room.localParticipant.setMicrophoneEnabled(true, {
        deviceId,
      })
      setRevision((current) => current + 1)
    }
  }

  function selectAudioOutputDevice(deviceId: string) {
    setAudioOutputDeviceId(deviceId)
  }

  async function selectVideoDevice(deviceId: string) {
    setVideoDeviceId(deviceId)

    if (room && cameraEnabled) {
      await room.localParticipant.setCameraEnabled(true, {
        deviceId,
        frameRate: 30,
        resolution: LANDSCAPE_VIDEO,
      })
      setRevision((current) => current + 1)
    }
  }

  function retryPreview() {
    setMicEnabled(true)
    setCameraEnabled(true)
    setPreviewErrorMessage(null)
    setPreviewRequestKey((current) => current + 1)
  }

  return (
    <main className="min-h-[calc(100svh-4rem)] bg-background text-foreground">
      <div className="flex min-h-[calc(100svh-4rem)] flex-col">
        <div
          className={cn(
            "flex w-full flex-1 flex-col",
            isConnected
              ? "gap-0 px-0 pb-0"
              : "mx-auto max-w-6xl gap-6 px-6 pb-12"
          )}
        >
          {errorMessage ? (
            <Alert variant="destructive" className="mx-auto w-full max-w-3xl">
              <AlertCircleIcon />
              <AlertTitle>Connection needs attention</AlertTitle>
              <AlertDescription>{errorMessage}</AlertDescription>
            </Alert>
          ) : null}

          {isConnected ? (
            <ConnectedMeeting
              room={room}
              participants={participants}
              participantName={participantName}
              translationLanguage={translationLanguage}
              micEnabled={micEnabled}
              cameraEnabled={cameraEnabled}
              audioInputs={audioInputs}
              audioOutputs={audioOutputs}
              videoInputs={videoInputs}
              audioDeviceId={audioDeviceId}
              audioOutputDeviceId={audioOutputDeviceId}
              videoDeviceId={videoDeviceId}
              onCopyRoomUrl={copyRoomUrl}
              onLeaveRoom={leaveRoom}
              onTranslationLanguageChange={setTranslationLanguage}
              onAudioDeviceChange={(deviceId) => {
                void selectAudioDevice(deviceId)
              }}
              onAudioOutputDeviceChange={selectAudioOutputDevice}
              onToggleCamera={() => {
                void toggleCamera()
              }}
              onToggleMicrophone={() => {
                void toggleMicrophone()
              }}
              onVideoDeviceChange={(deviceId) => {
                void selectVideoDevice(deviceId)
              }}
            />
          ) : (
            <form
              onSubmit={joinRoom}
              className="grid flex-1 content-center items-start gap-12 py-8 md:grid-cols-[minmax(0,1fr)_18rem] lg:grid-cols-[minmax(0,44rem)_22rem]"
            >
              <section className="flex flex-col items-center gap-4">
                <div className="relative grid aspect-video w-full max-w-[43rem] place-items-center overflow-hidden rounded-xl bg-foreground text-background shadow-lg">
                  <Badge
                    variant="secondary"
                    className="absolute end-4 top-4 z-10"
                  >
                    HD
                  </Badge>

                  {previewStream && cameraEnabled ? (
                    <video
                      ref={previewVideoRef}
                      autoPlay
                      muted
                      playsInline
                      className="size-full scale-x-[-1] object-contain"
                    />
                  ) : previewErrorMessage ? (
                    <div className="flex flex-col items-center gap-5 px-6 text-center text-background">
                      <p className="text-xl font-medium">Camera blocked</p>
                      <Button type="button" onClick={retryPreview}>
                        Retry
                      </Button>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-3 text-center text-background/70">
                      <VideoOffIcon className="size-10" />
                    </div>
                  )}

                  <div className="absolute inset-x-0 bottom-5 flex items-center justify-center gap-3">
                    <Button
                      type="button"
                      variant="secondary"
                      size="icon"
                      className="rounded-full"
                    >
                      <BrandIcon src="/icons/ellipsis.svg" alt="" />
                    </Button>
                    <Button
                      type="button"
                      variant={micEnabled ? "secondary" : "destructive"}
                      size="icon"
                      className="rounded-full"
                      onClick={() => {
                        void toggleMicrophone()
                      }}
                    >
                      <BrandIcon
                        src={
                          micEnabled
                            ? "/icons/microphone.svg"
                            : "/icons/microphone-slash.svg"
                        }
                        alt=""
                      />
                    </Button>
                    <Button
                      type="button"
                      variant={cameraEnabled ? "secondary" : "destructive"}
                      size="icon"
                      className="rounded-full"
                      onClick={() => {
                        void toggleCamera()
                      }}
                    >
                      <BrandIcon
                        src={
                          cameraEnabled
                            ? "/icons/camera.svg"
                            : "/icons/video-slash.svg"
                        }
                        alt=""
                      />
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      size="icon"
                      className="rounded-full"
                    >
                      <BrandIcon src="/icons/settings.svg" alt="" />
                    </Button>
                  </div>
                </div>

                <div className="flex w-full max-w-[43rem] flex-wrap justify-center gap-2">
                  {hasMounted ? (
                    <>
                      <DeviceSelect
                        value={audioDeviceId}
                        onValueChange={setAudioDeviceId}
                        placeholder="Microphone"
                        iconSrc="/icons/microphone.svg"
                      >
                        {audioInputs.map((device, index) => (
                          <SelectItem
                            key={device.deviceId}
                            value={device.deviceId}
                          >
                            {getDeviceLabel(device, "Microphone", index)}
                          </SelectItem>
                        ))}
                      </DeviceSelect>
                      <DeviceSelect
                        value={videoDeviceId}
                        onValueChange={setVideoDeviceId}
                        placeholder="Camera"
                        iconSrc="/icons/camera.svg"
                      >
                        {videoInputs.map((device, index) => (
                          <SelectItem
                            key={device.deviceId}
                            value={device.deviceId}
                          >
                            {getDeviceLabel(device, "Camera", index)}
                          </SelectItem>
                        ))}
                      </DeviceSelect>
                    </>
                  ) : (
                    <>
                      <DeviceSelectShell
                        placeholder="Microphone"
                        iconSrc="/icons/microphone.svg"
                      />
                      <DeviceSelectShell
                        placeholder="Camera"
                        iconSrc="/icons/camera.svg"
                      />
                    </>
                  )}
                </div>
              </section>

              <section className="mx-auto flex w-full max-w-sm flex-col items-stretch text-left">
                <div className="flex flex-col gap-4">
                  <label className="flex flex-col gap-2 font-sans text-base font-medium tracking-normal text-foreground">
                    <span>Meeting code</span>
                    <Input
                      aria-label="Meeting code"
                      autoComplete="off"
                      className="h-12 w-full rounded-full border border-foreground/25 bg-background px-4 font-sans text-base tracking-normal text-foreground placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:ring-foreground/20 md:text-base"
                      maxLength={120}
                      placeholder="room-123"
                      value={roomName}
                      onChange={(event) => setRoomName(event.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-2 font-sans text-base font-medium tracking-normal text-foreground">
                    <span>Name</span>
                    <Input
                      aria-label="Your name"
                      autoComplete="name"
                      className="h-12 w-full rounded-full border border-foreground/25 bg-background px-4 font-sans text-base tracking-normal text-foreground placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:ring-foreground/20 md:text-base"
                      maxLength={80}
                      placeholder="Blossom"
                      value={participantName}
                      onChange={(event) =>
                        setParticipantName(event.target.value)
                      }
                    />
                  </label>
                </div>
                <LobbyPresence participants={lobbyParticipants} />
                <Button
                  type="submit"
                  size="lg"
                  className="mt-8 h-12 w-full rounded-full bg-foreground font-sans text-base font-medium tracking-normal text-background hover:bg-foreground/90"
                  disabled={joinState === "connecting"}
                >
                  {joinState === "connecting" ? (
                    <Spinner data-icon="inline-start" />
                  ) : null}
                  Join now
                </Button>
              </section>
            </form>
          )}
        </div>
      </div>
    </main>
  )
}

function LobbyPresence({
  participants,
}: {
  participants: ParticipantPresence[]
}) {
  if (participants.length === 0) {
    return (
      <p className="mt-5 font-sans text-base font-medium tracking-normal text-muted-foreground">
        No one else is here
      </p>
    )
  }

  return (
    <div className="mt-5 flex flex-wrap gap-2">
      {participants.map((participant) => (
        <Badge key={participant.identity} variant="secondary">
          {participant.name}
        </Badge>
      ))}
    </div>
  )
}

function BrandIcon({
  src,
  alt,
  className,
}: {
  src: string
  alt: string
  className?: string
}) {
  return (
    <Image
      src={src}
      alt={alt}
      width={20}
      height={20}
      className={cn("size-5 dark:invert", className)}
    />
  )
}

function DeviceSelect({
  value,
  onValueChange,
  placeholder,
  iconSrc,
  disabled,
  children,
}: {
  value: string
  onValueChange: (value: string) => void
  placeholder: string
  iconSrc: string
  disabled?: boolean
  children: React.ReactNode
}) {
  return (
    <Select value={value} onValueChange={onValueChange} disabled={disabled}>
      <SelectTrigger className="h-9 w-72 max-w-[calc(100vw-3rem)] rounded-full border bg-background">
        <BrandIcon src={iconSrc} alt="" />
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>{children}</SelectGroup>
      </SelectContent>
    </Select>
  )
}

function DeviceSelectShell({
  placeholder,
  iconSrc,
}: {
  placeholder: string
  iconSrc: string
}) {
  return (
    <button
      type="button"
      tabIndex={-1}
      className="flex h-9 max-w-52 items-center justify-between gap-1.5 rounded-full border bg-background px-3 py-2 text-sm text-muted-foreground"
      aria-hidden="true"
    >
      <BrandIcon src={iconSrc} alt="" />
      <span>{placeholder}</span>
    </button>
  )
}

function ConnectedMeeting({
  room,
  participants,
  participantName,
  translationLanguage,
  micEnabled,
  cameraEnabled,
  audioInputs,
  audioOutputs,
  videoInputs,
  audioDeviceId,
  audioOutputDeviceId,
  videoDeviceId,
  onCopyRoomUrl,
  onLeaveRoom,
  onTranslationLanguageChange,
  onAudioDeviceChange,
  onAudioOutputDeviceChange,
  onToggleCamera,
  onToggleMicrophone,
  onVideoDeviceChange,
}: {
  room: Room
  participants: Participant[]
  participantName: string
  translationLanguage: string
  micEnabled: boolean
  cameraEnabled: boolean
  audioInputs: MediaDeviceInfo[]
  audioOutputs: MediaDeviceInfo[]
  videoInputs: MediaDeviceInfo[]
  audioDeviceId: string
  audioOutputDeviceId: string
  videoDeviceId: string
  onCopyRoomUrl: () => void
  onLeaveRoom: () => void
  onTranslationLanguageChange: (language: string) => void
  onAudioDeviceChange: (deviceId: string) => void
  onAudioOutputDeviceChange: (deviceId: string) => void
  onToggleCamera: () => void
  onToggleMicrophone: () => void
  onVideoDeviceChange: (deviceId: string) => void
}) {
  const localParticipant = room.localParticipant
  const remoteParticipants = participants.filter(
    (participant) => participant !== localParticipant
  )
  const localName =
    localParticipant.name || participantName.trim() || DEFAULT_PARTICIPANT_NAME
  const visibleRemoteParticipants = remoteParticipants.slice(
    0,
    MAX_VISIBLE_PARTICIPANTS - 1
  )
  const meetingParticipants: MeetingTileModel[] = [
    {
      participant: localParticipant,
      label: localName,
      isLocal: true,
      highlighted: true,
      visualIndex: visibleRemoteParticipants.length,
    },
    ...visibleRemoteParticipants.map((participant, index) => ({
      participant,
      label: getParticipantLabel(participant, index + 1),
      isLocal: false,
      highlighted: false,
      visualIndex: index,
    })),
  ]
  const [openDeviceMenu, setOpenDeviceMenu] =
    React.useState<DeviceMenuKind | null>(null)
  const [quickTranslationMenuOpen, setQuickTranslationMenuOpen] =
    React.useState(false)
  const [translationSettingsOpen, setTranslationSettingsOpen] =
    React.useState(false)
  const translationPanelRef = React.useRef<HTMLDivElement | null>(null)
  const translationTriggerRef = React.useRef<HTMLDivElement | null>(null)
  const [translationEnabled, setTranslationEnabled] = React.useState(false)
  const [captionsEnabled, setCaptionsEnabled] = React.useState(true)
  const [sourceTranscriptionEnabled, setSourceTranscriptionEnabled] =
    React.useState(false)
  const [translationMix, setTranslationMix] = React.useState(85)
  const [participantTranslations, setParticipantTranslations] = React.useState<
    Record<string, ParticipantTranslationSnapshot>
  >({})
  const localAudioLevel = useParticipantAudioLevel(localParticipant, micEnabled)
  const hasRemoteAudioTrack = visibleRemoteParticipants.some((participant) =>
    Boolean(getParticipantAudioMediaStreamTrack(participant))
  )
  const translatedVolume = translationEnabled ? translationMix / 100 : 0
  const sourceVolume = translationEnabled ? (100 - translationMix) / 100 : 1
  const translationStatus = getAggregateTranslationStatus(
    visibleRemoteParticipants.map(
      (participant) => participantTranslations[participant.identity]
    )
  )
  const translationError =
    visibleRemoteParticipants
      .map(
        (participant) => participantTranslations[participant.identity]?.error
      )
      .find(Boolean) ?? null

  const updateParticipantTranslation = React.useCallback(
    (nextTranslation: ParticipantTranslationSnapshot) => {
      setParticipantTranslations((current) => {
        const previous = current[nextTranslation.participantId]

        if (areParticipantTranslationsEqual(previous, nextTranslation)) {
          return current
        }

        return {
          ...current,
          [nextTranslation.participantId]: nextTranslation,
        }
      })
    },
    []
  )

  const removeParticipantTranslation = React.useCallback(
    (participantId: string) => {
      setParticipantTranslations((current) => {
        if (!current[participantId]) {
          return current
        }

        const nextTranslations = { ...current }
        delete nextTranslations[participantId]
        return nextTranslations
      })
    },
    []
  )

  function setDeviceMenuOpen(menu: DeviceMenuKind, open: boolean) {
    if (open) {
      setQuickTranslationMenuOpen(false)
      setTranslationSettingsOpen(false)
    }

    setOpenDeviceMenu((current) =>
      open ? menu : current === menu ? null : current
    )
  }

  React.useEffect(() => {
    if (!translationSettingsOpen) {
      return
    }

    function targetIsWithinTranslationControls(target: EventTarget | null) {
      if (!(target instanceof Node)) {
        return false
      }

      if (
        translationPanelRef.current?.contains(target) ||
        translationTriggerRef.current?.contains(target)
      ) {
        return true
      }

      return (
        target instanceof Element &&
        target.closest('[data-slot="select-content"]') !== null
      )
    }

    function handlePointerDown(event: PointerEvent) {
      if (!targetIsWithinTranslationControls(event.target)) {
        setTranslationSettingsOpen(false)
      }
    }

    function handleFocusIn(event: FocusEvent) {
      if (!targetIsWithinTranslationControls(event.target)) {
        setTranslationSettingsOpen(false)
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setTranslationSettingsOpen(false)
      }
    }

    document.addEventListener("pointerdown", handlePointerDown, true)
    document.addEventListener("focusin", handleFocusIn, true)
    document.addEventListener("keydown", handleKeyDown)

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown, true)
      document.removeEventListener("focusin", handleFocusIn, true)
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [translationSettingsOpen])

  return (
    <section className="relative mx-[calc(50%-50vw)] flex h-[calc(100svh-4rem)] min-h-0 w-screen overflow-hidden bg-background text-foreground dark:bg-black dark:text-white">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div
          className={cn(
            "grid min-h-0 flex-1 auto-rows-fr gap-3 p-4",
            getMeetingGridClassName(meetingParticipants.length)
          )}
        >
          {meetingParticipants.map((tile) => {
            const tileClassName = cn(
              "bg-zinc-900 dark:bg-black",
              getMeetingTileOrderClassName(tile.visualIndex),
              getMeetingTileClassName(
                tile.visualIndex,
                meetingParticipants.length
              )
            )

            if (tile.isLocal) {
              return (
                <MeetingTile
                  key={tile.participant.identity}
                  participant={tile.participant}
                  label={tile.label}
                  isLocal={tile.isLocal}
                  highlighted={tile.highlighted}
                  audioOutputDeviceId={audioOutputDeviceId}
                  tileClassName={tileClassName}
                />
              )
            }

            return (
              <TranslatedMeetingTile
                key={tile.participant.identity}
                tile={tile}
                audioOutputDeviceId={audioOutputDeviceId}
                captionsEnabled={captionsEnabled}
                language={translationLanguage}
                sourceTranscriptionEnabled={sourceTranscriptionEnabled}
                sourceTranscriptionVisible={sourceTranscriptionEnabled}
                sourceVolume={sourceVolume}
                tileClassName={tileClassName}
                translatedVolume={translatedVolume}
                translationEnabled={translationEnabled}
                onTranslationChange={updateParticipantTranslation}
                onTranslationRemove={removeParticipantTranslation}
              />
            )
          })}
        </div>

        <div className="shrink-0 px-6 pb-5">
          <div className="grid items-center gap-4 md:grid-cols-[1fr_auto_1fr]">
            <div className="flex justify-center md:col-start-1 md:justify-start">
              <QuickTranslationPicker
                open={quickTranslationMenuOpen}
                enabled={translationEnabled}
                language={translationLanguage}
                onOpenChange={(open) => {
                  setQuickTranslationMenuOpen(open)
                  if (open) {
                    setOpenDeviceMenu(null)
                    setTranslationSettingsOpen(false)
                  }
                }}
                onSelectLanguage={(language) => {
                  onTranslationLanguageChange(language)
                  setTranslationEnabled(true)
                  setQuickTranslationMenuOpen(false)
                }}
                onSelectOff={() => {
                  setTranslationEnabled(false)
                  setQuickTranslationMenuOpen(false)
                }}
              />
            </div>

            <div className="flex items-center justify-center gap-2 md:col-start-2">
              <div ref={translationTriggerRef}>
                <InCallIconButton
                  ariaLabel={
                    translationSettingsOpen
                      ? "Close translation"
                      : "Open translation"
                  }
                  selected={translationSettingsOpen || translationEnabled}
                  onClick={() => {
                    setOpenDeviceMenu(null)
                    setTranslationSettingsOpen((current) => !current)
                  }}
                >
                  <BrandIcon src="/icons/ellipsis.svg" alt="" />
                </InCallIconButton>
              </div>
              <InCallDeviceControl
                active={micEnabled}
                icon={
                  <BrandIcon
                    src={
                      micEnabled
                        ? "/icons/microphone.svg"
                        : "/icons/microphone-slash.svg"
                    }
                    alt=""
                    className={cn(!micEnabled && "invert")}
                  />
                }
                audioLevel={localAudioLevel}
                menuOpen={openDeviceMenu === "audio"}
                menuLabel="Audio devices"
                toggleLabel={
                  micEnabled ? "Mute microphone" : "Unmute microphone"
                }
                onMenuOpenChange={(open) => setDeviceMenuOpen("audio", open)}
                onToggle={() => {
                  setOpenDeviceMenu(null)
                  onToggleMicrophone()
                }}
                menu={
                  <DeviceMenu
                    sections={[
                      {
                        label: "Microphone",
                        emptyLabel: "No microphones",
                        options: audioInputs.map((device, index) => ({
                          id: device.deviceId,
                          label: getDeviceLabel(device, "Microphone", index),
                          selected: device.deviceId === audioDeviceId,
                          onSelect: () => onAudioDeviceChange(device.deviceId),
                        })),
                      },
                      {
                        label: "Speakers",
                        emptyLabel: "Default speaker",
                        options:
                          audioOutputs.length > 0
                            ? audioOutputs.map((device, index) => ({
                                id: device.deviceId,
                                label: getDeviceLabel(device, "Speaker", index),
                                selected:
                                  device.deviceId === audioOutputDeviceId,
                                onSelect: () =>
                                  onAudioOutputDeviceChange(device.deviceId),
                              }))
                            : [
                                {
                                  id: "default",
                                  label: "Default speaker",
                                  selected: !audioOutputDeviceId,
                                  onSelect: () => onAudioOutputDeviceChange(""),
                                },
                              ],
                      },
                    ]}
                  />
                }
              />
              <InCallDeviceControl
                active={cameraEnabled}
                icon={
                  <BrandIcon
                    src={
                      cameraEnabled
                        ? "/icons/camera.svg"
                        : "/icons/video-slash.svg"
                    }
                    alt=""
                    className={cn(!cameraEnabled && "invert")}
                  />
                }
                menuOpen={openDeviceMenu === "video"}
                menuLabel="Camera devices"
                toggleLabel={
                  cameraEnabled ? "Turn camera off" : "Turn camera on"
                }
                onMenuOpenChange={(open) => setDeviceMenuOpen("video", open)}
                onToggle={() => {
                  setOpenDeviceMenu(null)
                  onToggleCamera()
                }}
                menu={
                  <DeviceMenu
                    sections={[
                      {
                        label: "Camera",
                        emptyLabel: "No cameras",
                        options: videoInputs.map((device, index) => ({
                          id: device.deviceId,
                          label: getDeviceLabel(device, "Camera", index),
                          selected: device.deviceId === videoDeviceId,
                          onSelect: () => onVideoDeviceChange(device.deviceId),
                        })),
                      },
                    ]}
                  />
                }
              />
              <button
                type="button"
                aria-label="Leave"
                className="grid h-11 w-16 cursor-pointer place-items-center rounded-full bg-[#d84a38] text-white transition hover:bg-[#c23b2b]"
                onClick={onLeaveRoom}
              >
                <PhoneOffIcon className="size-5" />
              </button>
            </div>

            <div className="flex justify-center gap-2 md:col-start-3 md:justify-end">
              <InCallIconButton
                ariaLabel="Copy room link"
                onClick={onCopyRoomUrl}
              >
                <CopyIcon className="size-5" />
              </InCallIconButton>
            </div>
          </div>

          {translationSettingsOpen ? (
            <TranslationPanel
              rootRef={translationPanelRef}
              enabled={translationEnabled}
              language={translationLanguage}
              captionsEnabled={captionsEnabled}
              sourceTranscriptionEnabled={sourceTranscriptionEnabled}
              mix={translationMix}
              status={translationStatus}
              error={translationError}
              disabled={!hasRemoteAudioTrack}
              onCaptionsEnabledChange={setCaptionsEnabled}
              onEnabledChange={setTranslationEnabled}
              onLanguageChange={onTranslationLanguageChange}
              onMixChange={setTranslationMix}
              onSourceTranscriptionEnabledChange={setSourceTranscriptionEnabled}
            />
          ) : null}
        </div>
      </div>

    </section>
  )
}

function getParticipantLabel(participant: Participant, position: number) {
  return participant.name || participant.identity || `Participant ${position}`
}

function useParticipantAudioLevel(participant: Participant, enabled: boolean) {
  const [level, setLevel] = React.useState(0)

  React.useEffect(() => {
    if (!enabled) {
      return
    }

    let frame = 0
    let displayedLevel = 0

    function updateLevel() {
      const liveLevel = enabled ? participant.audioLevel : 0
      const amplifiedLevel =
        liveLevel > SPEAKING_LEVEL_FLOOR
          ? Math.min(1, liveLevel * 1.8 + 0.08)
          : 0
      const nextLevel =
        amplifiedLevel > displayedLevel
          ? amplifiedLevel
          : Math.max(0, displayedLevel * 0.82)

      if (Math.abs(nextLevel - displayedLevel) > 0.01) {
        displayedLevel = nextLevel
        setLevel(nextLevel)
      } else if (displayedLevel !== 0 && nextLevel < 0.02) {
        displayedLevel = 0
        setLevel(0)
      }

      frame = window.requestAnimationFrame(updateLevel)
    }

    updateLevel()

    return () => {
      window.cancelAnimationFrame(frame)
    }
  }, [enabled, participant])

  return enabled ? level : 0
}

function getMeetingGridClassName(participantCount: number) {
  if (participantCount <= 1) {
    return "grid-cols-1"
  }

  if (participantCount <= 4) {
    return "grid-cols-1 md:grid-cols-2"
  }

  return "grid-cols-1 sm:grid-cols-2 xl:grid-cols-6"
}

function getMeetingTileClassName(index: number, participantCount: number) {
  if (participantCount === 3 && index === 2) {
    return "md:col-span-2 md:mx-auto md:w-1/2"
  }

  if (participantCount >= 5) {
    return cn(
      "xl:col-span-2",
      participantCount === 5 && index === 3 && "xl:col-start-2"
    )
  }

  return undefined
}

function getMeetingTileOrderClassName(index: number) {
  switch (index) {
    case 0:
      return "order-1"
    case 1:
      return "order-2"
    case 2:
      return "order-3"
    case 3:
      return "order-4"
    case 4:
      return "order-5"
    default:
      return "order-6"
  }
}

function TranslatedMeetingTile({
  tile,
  audioOutputDeviceId,
  captionsEnabled,
  language,
  sourceTranscriptionEnabled,
  sourceTranscriptionVisible,
  sourceVolume,
  tileClassName,
  translatedVolume,
  translationEnabled,
  onTranslationChange,
  onTranslationRemove,
}: {
  tile: MeetingTileModel
  audioOutputDeviceId?: string
  captionsEnabled: boolean
  language: string
  sourceTranscriptionEnabled: boolean
  sourceTranscriptionVisible: boolean
  sourceVolume: number
  tileClassName?: string
  translatedVolume: number
  translationEnabled: boolean
  onTranslationChange: (translation: ParticipantTranslationSnapshot) => void
  onTranslationRemove: (participantId: string) => void
}) {
  const sourceTrack = getParticipantAudioMediaStreamTrack(tile.participant)
  const translationActive = Boolean(
    sourceTrack && (translationEnabled || sourceTranscriptionEnabled)
  )
  const translation = useRemoteTranslation({
    enabled: translationActive,
    sourceTrack,
    language,
    sourceTranscriptionEnabled,
    noiseReductionEnabled: false,
    translatedVolume,
  })
  const participantId = tile.participant.identity

  React.useEffect(() => {
    onTranslationChange({
      participantId,
      participantName: tile.label,
      hasSourceTrack: Boolean(sourceTrack),
      status: sourceTrack ? translation.status : "idle",
      error: sourceTrack ? translation.error : null,
      sourceTranscript: sourceTrack ? translation.sourceTranscript : "",
      translatedTranscript: sourceTrack ? translation.translatedTranscript : "",
      sourceSubtitle: sourceTrack ? translation.sourceSubtitle : "",
      translatedSubtitle: sourceTrack ? translation.translatedSubtitle : "",
      hasOutputAudio: sourceTrack ? translation.hasOutputAudio : false,
    })
  }, [
    onTranslationChange,
    participantId,
    sourceTrack,
    tile.label,
    translation.error,
    translation.hasOutputAudio,
    translation.sourceSubtitle,
    translation.sourceTranscript,
    translation.status,
    translation.translatedSubtitle,
    translation.translatedTranscript,
  ])

  React.useEffect(() => {
    return () => {
      onTranslationRemove(participantId)
    }
  }, [onTranslationRemove, participantId])

  return (
    <MeetingTile
      participant={tile.participant}
      label={tile.label}
      isLocal={tile.isLocal}
      highlighted={tile.highlighted}
      audioOutputDeviceId={audioOutputDeviceId}
      sourceVolume={
        translationEnabled && sourceTrack && translation.hasOutputAudio
          ? sourceVolume
          : 1
      }
      sourceSubtitle={
        captionsEnabled && sourceTranscriptionVisible
          ? translation.sourceSubtitle
          : ""
      }
      translatedSubtitle={
        translationEnabled && captionsEnabled
          ? translation.translatedSubtitle
          : ""
      }
      tileClassName={tileClassName}
    />
  )
}

function MeetingTile({
  participant,
  label,
  isLocal,
  highlighted,
  audioOutputDeviceId,
  sourceVolume = 1,
  sourceSubtitle,
  translatedSubtitle,
  tileClassName,
}: {
  participant: Participant
  label: string
  isLocal?: boolean
  highlighted?: boolean
  audioOutputDeviceId?: string
  sourceVolume?: number
  sourceSubtitle?: string
  translatedSubtitle?: string
  tileClassName?: string
}) {
  const videoRef = React.useRef<HTMLVideoElement | null>(null)
  const audioRef = React.useRef<HTMLAudioElement | null>(null)

  const videoPublication = participant.getTrackPublication(Track.Source.Camera)
  const audioPublication = participant.getTrackPublication(
    Track.Source.Microphone
  )
  const videoTrack = videoPublication?.videoTrack
  const audioTrack = audioPublication?.audioTrack

  React.useEffect(() => {
    const element = videoRef.current
    if (!element || !videoTrack) {
      return
    }

    videoTrack.attach(element)

    return () => {
      videoTrack.detach(element)
    }
  }, [videoTrack])

  React.useEffect(() => {
    const element = audioRef.current
    if (!element || !audioTrack || isLocal) {
      return
    }

    audioTrack.attach(element)
    element.volume = sourceVolume

    return () => {
      audioTrack.detach(element)
    }
  }, [audioTrack, isLocal, sourceVolume])

  React.useEffect(() => {
    if (audioRef.current) {
      audioRef.current.volume = sourceVolume
    }
  }, [sourceVolume])

  React.useEffect(() => {
    const element = audioRef.current as
      | (HTMLAudioElement & { setSinkId?: (sinkId: string) => Promise<void> })
      | null

    if (!element?.setSinkId) {
      return
    }

    element.setSinkId(audioOutputDeviceId || "").catch(() => {})
  }, [audioOutputDeviceId])

  return (
    <div
      className={cn(
        "relative grid min-h-0 overflow-hidden rounded-2xl ring-1 ring-border",
        "shadow-[0_1px_0_rgba(255,255,255,0.5)_inset] dark:shadow-[0_1px_0_rgba(255,255,255,0.08)_inset] dark:ring-white/10",
        highlighted && "ring-2 ring-[#8ab4f8]",
        tileClassName
      )}
    >
      {videoTrack ? (
        <video
          ref={videoRef}
          autoPlay
          muted={isLocal}
          playsInline
          className={cn("size-full object-contain", isLocal && "scale-x-[-1]")}
        />
      ) : (
        <div className="grid size-full place-items-center">
          <div className="grid size-16 place-items-center rounded-full bg-white/20 text-2xl font-medium">
            {getInitial(label)}
          </div>
        </div>
      )}
      {!isLocal ? <audio ref={audioRef} autoPlay /> : null}
      {translatedSubtitle || sourceSubtitle ? (
        <div className="pointer-events-none absolute inset-x-5 bottom-14 flex flex-col items-center gap-1 text-center">
          {translatedSubtitle ? (
            <p className="max-w-3xl rounded-xl bg-black/70 px-3 py-2 text-base leading-snug font-medium text-white shadow-lg">
              {translatedSubtitle}
            </p>
          ) : null}
          {sourceSubtitle ? (
            <p className="max-w-2xl rounded-lg bg-black/45 px-2.5 py-1.5 text-xs leading-snug font-medium text-white/85">
              {sourceSubtitle}
            </p>
          ) : null}
        </div>
      ) : null}
      <div className="absolute start-4 bottom-4 flex items-center gap-2 text-sm font-medium text-white">
        {audioPublication?.isMuted ? <VideoOffIcon className="size-4" /> : null}
        <span className="drop-shadow">{label}</span>
      </div>
    </div>
  )
}

function TranslationPanel({
  rootRef,
  enabled,
  language,
  captionsEnabled,
  sourceTranscriptionEnabled,
  mix,
  status,
  error,
  disabled,
  onCaptionsEnabledChange,
  onEnabledChange,
  onLanguageChange,
  onMixChange,
  onSourceTranscriptionEnabledChange,
}: {
  rootRef?: React.Ref<HTMLDivElement>
  enabled: boolean
  language: string
  captionsEnabled: boolean
  sourceTranscriptionEnabled: boolean
  mix: number
  status: "idle" | "connecting" | "connected" | "error"
  error: string | null
  disabled: boolean
  onCaptionsEnabledChange: (enabled: boolean) => void
  onEnabledChange: (enabled: boolean) => void
  onLanguageChange: (language: string) => void
  onMixChange: (mix: number) => void
  onSourceTranscriptionEnabledChange: (enabled: boolean) => void
}) {
  return (
    <div
      ref={rootRef}
      className="absolute bottom-20 left-1/2 z-20 flex w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 flex-col gap-4 rounded-2xl border border-border bg-background p-4 shadow-xl dark:border-white/15 dark:bg-black"
    >
      <div className="flex items-center justify-between gap-4">
        <span className="text-sm font-medium">Translation</span>
        <Switch
          checked={enabled}
          disabled={disabled}
          aria-label="Translation"
          onCheckedChange={onEnabledChange}
        />
      </div>

      <label className="flex items-center justify-between gap-4 text-sm font-medium">
        <span>Preferred Output language</span>
        <OutputLanguageSelect
          value={language}
          disabled={enabled && status === "connecting"}
          triggerClassName="h-9 w-44 rounded-full border bg-background"
          onValueChange={onLanguageChange}
        />
      </label>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-sm font-medium">
          <span>Audio mix</span>
          <span className="text-muted-foreground dark:text-white/60">
            {mix}%
          </span>
        </div>
        <Slider
          value={[mix]}
          min={0}
          max={100}
          step={5}
          aria-label="Translated audio mix"
          onValueChange={(value) => onMixChange(value[0] ?? mix)}
        />
        <div className="flex items-center justify-between text-xs font-medium text-muted-foreground dark:text-white/60">
          <span>Original {100 - mix}%</span>
          <span>Translated {mix}%</span>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <TranslationSwitch
          checked={captionsEnabled}
          label="Captions"
          onCheckedChange={onCaptionsEnabledChange}
        />
        <TranslationSwitch
          checked={sourceTranscriptionEnabled}
          label="Source text"
          onCheckedChange={onSourceTranscriptionEnabledChange}
        />
      </div>

      {status === "connecting" ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground dark:text-white/70">
          <Spinner data-icon="inline-start" />
          <span>Connecting</span>
        </div>
      ) : null}

      {error ? (
        <p className="text-sm font-medium text-destructive">{error}</p>
      ) : null}
    </div>
  )
}

function OutputLanguageSelect({
  value,
  disabled,
  triggerClassName,
  onValueChange,
}: {
  value: string
  disabled?: boolean
  triggerClassName?: string
  onValueChange: (language: string) => void
}) {
  const hasMounted = useMounted()
  const selectedLabel = getTranslationLanguageLabel(value)

  if (!hasMounted) {
    return (
      <button
        type="button"
        aria-disabled="true"
        aria-label="Preferred Output language"
        className={cn(
          "flex items-center justify-between gap-1.5 whitespace-nowrap",
          triggerClassName
        )}
      >
        <span className="truncate">{selectedLabel}</span>
        <ChevronDownIcon className="pointer-events-none size-4 shrink-0 text-muted-foreground" />
      </button>
    )
  }

  return (
    <Select value={value} disabled={disabled} onValueChange={onValueChange}>
      <SelectTrigger
        aria-label="Preferred Output language"
        className={triggerClassName}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          {TRANSLATION_LANGUAGES.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  )
}

function getTranslationLanguageLabel(value: string) {
  return (
    TRANSLATION_LANGUAGES.find((option) => option.value === value)?.label ||
    value
  )
}

async function copyTextToClipboard(text: string) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return
    }
  } catch {
    // Fall back below for browser surfaces that block Clipboard API writes.
  }

  const textarea = document.createElement("textarea")
  textarea.value = text
  textarea.setAttribute("readonly", "")
  textarea.style.position = "fixed"
  textarea.style.opacity = "0"
  textarea.style.pointerEvents = "none"
  document.body.appendChild(textarea)
  textarea.select()

  try {
    document.execCommand("copy")
  } catch {
    return
  } finally {
    textarea.remove()
  }
}

function TranslationSwitch({
  checked,
  label,
  onCheckedChange,
}: {
  checked: boolean
  label: string
  onCheckedChange: (checked: boolean) => void
}) {
  return (
    <label className="flex items-center justify-between gap-2 rounded-xl bg-muted px-3 py-2 text-sm font-medium dark:bg-white/10">
      <span>{label}</span>
      <Switch
        size="sm"
        checked={checked}
        aria-label={label}
        onCheckedChange={onCheckedChange}
      />
    </label>
  )
}

function QuickTranslationPicker({
  open,
  enabled,
  language,
  onOpenChange,
  onSelectLanguage,
  onSelectOff,
}: {
  open: boolean
  enabled: boolean
  language: string
  onOpenChange: (open: boolean) => void
  onSelectLanguage: (language: string) => void
  onSelectOff: () => void
}) {
  const selectedLabel = enabled ? getTranslationLanguageLabel(language) : "Off"

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Translation language"
          aria-expanded={open}
          className={cn(
            "flex h-11 max-w-[13rem] cursor-pointer items-center gap-2 rounded-full px-3 text-sm font-medium transition",
            enabled
              ? "bg-[#d2e3fc] text-[#174ea6] hover:bg-[#c2d7f8] dark:bg-[#8ab4f8] dark:text-[#111213] dark:hover:bg-[#a8c7fa]"
              : "bg-muted text-foreground hover:bg-muted/80 dark:bg-black dark:text-white dark:ring-1 dark:ring-white/15 dark:hover:bg-black"
          )}
        >
          <LanguagesIcon className="size-4 shrink-0" />
          <span className="truncate">{selectedLabel}</span>
          <ChevronDownIcon
            className={cn(
              "size-4 shrink-0 transition-transform duration-200",
              open && "rotate-180"
            )}
          />
        </button>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="start"
        sideOffset={10}
        className="max-h-[min(28rem,calc(100svh-7rem))] w-56 overflow-y-auto rounded-2xl bg-[#151515] p-1.5 text-white shadow-2xl ring-1 ring-white/10"
      >
        <DeviceMenu
          sections={[
            {
              label: "Translation",
              emptyLabel: "No languages",
              options: [
                ...TRANSLATION_LANGUAGES.map((option) => ({
                  id: option.value,
                  label: option.label,
                  selected: enabled && option.value === language,
                  onSelect: () => onSelectLanguage(option.value),
                })),
                {
                  id: "off",
                  label: "Off",
                  selected: !enabled,
                  onSelect: onSelectOff,
                },
              ],
            },
          ]}
        />
      </PopoverContent>
    </Popover>
  )
}

function InCallDeviceControl({
  active,
  audioLevel = 0,
  icon,
  menu,
  menuLabel,
  menuOpen,
  toggleLabel,
  onMenuOpenChange,
  onToggle,
}: {
  active: boolean
  audioLevel?: number
  icon: React.ReactNode
  menu: React.ReactNode
  menuLabel: string
  menuOpen: boolean
  toggleLabel: string
  onMenuOpenChange: (open: boolean) => void
  onToggle: () => void
}) {
  return (
    <Popover open={menuOpen} onOpenChange={onMenuOpenChange}>
      <div
        className={cn(
          "flex h-11 overflow-hidden rounded-full transition",
          active
            ? "bg-muted text-foreground dark:bg-black dark:text-white dark:ring-1 dark:ring-white/15"
            : "bg-[#d84a38] text-white"
        )}
      >
        <button
          type="button"
          aria-label={toggleLabel}
          data-audio-active={audioLevel > 0}
          className={cn(
            "relative grid size-11 cursor-pointer place-items-center overflow-hidden transition",
            active
              ? "hover:bg-muted/80 dark:hover:bg-white/10"
              : "hover:bg-[#c23b2b]"
          )}
          onClick={onToggle}
        >
          {active ? (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-0 bottom-0 bg-[#8ab4f8]/35 transition-transform duration-75 ease-out dark:bg-[#8ab4f8]/45"
              style={{
                height: "100%",
                transform: `scaleY(${audioLevel})`,
                transformOrigin: "bottom",
              }}
            />
          ) : null}
          <span className="relative z-10 grid place-items-center">{icon}</span>
        </button>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label={menuLabel}
            aria-expanded={menuOpen}
            className={cn(
              "grid h-11 w-9 cursor-pointer place-items-center border-s transition",
              active
                ? "border-foreground/10 hover:bg-muted/80 dark:border-white/10 dark:hover:bg-white/10"
                : "border-white/15 hover:bg-[#c23b2b]"
            )}
          >
            <ChevronDownIcon
              className={cn(
                "size-4 transition-transform duration-200",
                menuOpen && "rotate-180"
              )}
            />
          </button>
        </PopoverTrigger>
      </div>
      <PopoverContent
        side="top"
        align="center"
        sideOffset={10}
        className="max-h-[min(24rem,calc(100svh-7rem))] w-64 overflow-y-auto rounded-2xl bg-[#151515] p-1.5 text-white shadow-2xl ring-1 ring-white/10"
      >
        {menu}
      </PopoverContent>
    </Popover>
  )
}

function DeviceMenu({ sections }: { sections: DeviceMenuSection[] }) {
  return (
    <div role="menu" className="flex flex-col gap-1">
      {sections.map((section, sectionIndex) => (
        <React.Fragment key={section.label}>
          <div className="flex flex-col gap-1">
            <div className="px-2.5 pt-1.5 pb-1 text-[11px] font-semibold text-white/45 uppercase">
              {section.label}
            </div>
            {section.options.length > 0 ? (
              section.options.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  role="menuitemradio"
                  aria-checked={option.selected}
                  disabled={option.disabled}
                  className={cn(
                    "flex h-10 w-full cursor-pointer items-center justify-between gap-3 rounded-xl px-3 text-left text-sm font-medium text-white/90 transition disabled:cursor-default disabled:opacity-50",
                    option.selected
                      ? "bg-white/10 text-white"
                      : "hover:bg-white/10"
                  )}
                  onClick={option.onSelect}
                >
                  <span className="truncate">{option.label}</span>
                  {option.selected ? (
                    <CheckIcon className="size-4 shrink-0 text-white/60" />
                  ) : null}
                </button>
              ))
            ) : (
              <div className="flex h-10 items-center rounded-xl px-3 text-sm font-medium text-white/45">
                {section.emptyLabel}
              </div>
            )}
          </div>
          {sectionIndex < sections.length - 1 ? (
            <Separator className="my-1 bg-white/10" />
          ) : null}
        </React.Fragment>
      ))}
    </div>
  )
}

function InCallIconButton({
  ariaLabel,
  active = true,
  selected = false,
  unreadCount = 0,
  onClick,
  children,
}: {
  ariaLabel: string
  active?: boolean
  selected?: boolean
  unreadCount?: number
  onClick?: () => void
  children: React.ReactNode
}) {
  const unreadLabel = unreadCount > 99 ? "99+" : `${unreadCount}`

  return (
    <button
      type="button"
      aria-label={ariaLabel}
      className={cn(
        "relative grid size-11 cursor-pointer place-items-center rounded-full transition",
        selected
          ? "bg-[#d2e3fc] text-[#174ea6] hover:bg-[#c2d7f8] dark:bg-[#8ab4f8] dark:text-[#111213] dark:hover:bg-[#a8c7fa]"
          : active
            ? "bg-muted text-foreground hover:bg-muted/80 dark:bg-black dark:text-white dark:ring-1 dark:ring-white/15 dark:hover:bg-black"
            : "bg-[#d84a38] text-white hover:bg-[#c23b2b]"
      )}
      onClick={onClick}
    >
      {children}
      {unreadCount > 0 ? (
        <span className="absolute -top-1 -right-1 grid min-w-5 place-items-center rounded-full bg-[#d84a38] px-1.5 text-[11px] leading-5 font-semibold text-white ring-2 ring-background dark:ring-black">
          {unreadLabel}
        </span>
      ) : null}
    </button>
  )
}

function getInitial(label: string) {
  return label.trim().charAt(0).toUpperCase() || "F"
}

function getParticipantAudioMediaStreamTrack(participant: Participant) {
  const audioTrack =
    participant.getTrackPublication(Track.Source.Microphone)?.audioTrack ?? null

  return getAudioMediaStreamTrack(audioTrack)
}

function getAggregateTranslationStatus(
  translations: Array<ParticipantTranslationSnapshot | undefined>
): TranslationStatus {
  const activeTranslations = translations.filter(
    (translation): translation is ParticipantTranslationSnapshot =>
      Boolean(translation?.hasSourceTrack)
  )

  if (
    activeTranslations.some((translation) => translation.status === "error")
  ) {
    return "error"
  }

  if (
    activeTranslations.some(
      (translation) => translation.status === "connecting"
    )
  ) {
    return "connecting"
  }

  if (
    activeTranslations.some((translation) => translation.status === "connected")
  ) {
    return "connected"
  }

  return "idle"
}

function areParticipantTranslationsEqual(
  previous: ParticipantTranslationSnapshot | undefined,
  next: ParticipantTranslationSnapshot
) {
  return (
    previous?.participantId === next.participantId &&
    previous.participantName === next.participantName &&
    previous.hasSourceTrack === next.hasSourceTrack &&
    previous.status === next.status &&
    previous.error === next.error &&
    previous.sourceTranscript === next.sourceTranscript &&
    previous.translatedTranscript === next.translatedTranscript &&
    previous.sourceSubtitle === next.sourceSubtitle &&
    previous.translatedSubtitle === next.translatedSubtitle &&
    previous.hasOutputAudio === next.hasOutputAudio
  )
}

function getAudioMediaStreamTrack(audioTrack: unknown) {
  if (!audioTrack || typeof audioTrack !== "object") {
    return null
  }

  const mediaStreamTrack = (audioTrack as { mediaStreamTrack?: unknown })
    .mediaStreamTrack

  return mediaStreamTrack instanceof MediaStreamTrack ? mediaStreamTrack : null
}

async function queryMediaPermission(name: MediaPermissionName) {
  if (!navigator.permissions?.query) {
    return null
  }

  try {
    return await navigator.permissions.query({
      name: name as PermissionName,
    })
  } catch {
    return null
  }
}

function stopMediaStream(stream: MediaStream | null) {
  stream?.getTracks().forEach((track) => track.stop())
}
