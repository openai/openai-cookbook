import {
  AccessToken,
  type AccessTokenOptions,
  type VideoGrant,
} from "livekit-server-sdk"
import { NextResponse } from "next/server"

import { getLiveKitEnv, normalizeLiveKitSegment } from "../livekit-env"

type TokenResponse = {
  serverUrl: string
  roomName: string
  participantName: string
  participantToken: string
}

export async function GET(request: Request) {
  try {
    const liveKitEnv = getLiveKitEnv()

    if (!liveKitEnv) {
      return new NextResponse(
        "Missing LIVEKIT_API_KEY, LIVEKIT_API_SECRET, or LIVEKIT_URL",
        { status: 500 }
      )
    }

    const url = new URL(request.url)
    const roomName = normalizeLiveKitSegment(url.searchParams.get("roomName"))
    const participantName = normalizeLiveKitSegment(
      url.searchParams.get("participantName")
    )

    if (!roomName) {
      return new NextResponse("Missing required query parameter: roomName", {
        status: 400,
      })
    }

    if (!participantName) {
      return new NextResponse(
        "Missing required query parameter: participantName",
        {
          status: 400,
        }
      )
    }

    const participantToken = await createParticipantToken(
      {
        identity: `${slugify(participantName)}-${crypto.randomUUID().slice(0, 8)}`,
        name: participantName,
      },
      roomName,
      liveKitEnv
    )

    const response: TokenResponse = {
      serverUrl: liveKitEnv.serverUrl,
      roomName,
      participantName,
      participantToken,
    }

    return NextResponse.json(response)
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unable to create LiveKit token"

    return new NextResponse(message, { status: 500 })
  }
}

function createParticipantToken(
  userInfo: AccessTokenOptions,
  roomName: string,
  liveKitEnv: NonNullable<ReturnType<typeof getLiveKitEnv>>
) {
  const accessToken = new AccessToken(
    liveKitEnv.apiKey,
    liveKitEnv.apiSecret,
    userInfo
  )
  accessToken.ttl = "30m"

  const grant: VideoGrant = {
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canPublishData: true,
    canSubscribe: true,
  }

  accessToken.addGrant(grant)

  return accessToken.toJwt()
}

function slugify(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "")
    .slice(0, 48)
}
