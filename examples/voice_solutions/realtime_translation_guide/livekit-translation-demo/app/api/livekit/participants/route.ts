import { RoomServiceClient, TwirpError } from "livekit-server-sdk"
import { NextResponse } from "next/server"

import { getLiveKitEnv, normalizeLiveKitSegment } from "../livekit-env"

type ParticipantPresence = {
  identity: string
  name: string
}

type ParticipantsResponse = {
  participants: ParticipantPresence[]
}

export async function GET(request: Request) {
  const liveKitEnv = getLiveKitEnv()

  if (!liveKitEnv) {
    return new NextResponse(
      "Missing LIVEKIT_API_KEY, LIVEKIT_API_SECRET, or LIVEKIT_URL",
      { status: 500 }
    )
  }

  const url = new URL(request.url)
  const roomName = normalizeLiveKitSegment(url.searchParams.get("roomName"))

  if (!roomName) {
    return new NextResponse("Missing required query parameter: roomName", {
      status: 400,
    })
  }

  const roomService = new RoomServiceClient(
    liveKitEnv.serverUrl,
    liveKitEnv.apiKey,
    liveKitEnv.apiSecret
  )

  try {
    const participants = await roomService.listParticipants(roomName)
    const response: ParticipantsResponse = {
      participants: participants.map((participant) => ({
        identity: participant.identity,
        name: participant.name || participant.identity,
      })),
    }

    return NextResponse.json(response)
  } catch (error) {
    if (error instanceof TwirpError && error.code === "not_found") {
      return NextResponse.json({
        participants: [],
      } satisfies ParticipantsResponse)
    }

    const message =
      error instanceof Error ? error.message : "Unable to list participants"

    return new NextResponse(message, { status: 500 })
  }
}
