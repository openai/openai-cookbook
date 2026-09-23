import { LiveKitVideoConference } from "@/components/conference/livekit-video-conference"

export default async function RoomPage({
  params,
}: {
  params: Promise<{ roomName: string }>
}) {
  const { roomName } = await params

  return <LiveKitVideoConference initialRoomName={roomName} />
}
