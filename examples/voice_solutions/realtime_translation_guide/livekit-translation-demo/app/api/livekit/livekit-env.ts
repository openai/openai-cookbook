import { loadEnvConfig } from "@next/env"

type LiveKitEnv = {
  apiKey: string
  apiSecret: string
  serverUrl: string
}

loadEnvConfig(process.cwd())

export function getLiveKitEnv(): LiveKitEnv | null {
  const apiKey = process.env.LIVEKIT_API_KEY
  const apiSecret = process.env.LIVEKIT_API_SECRET
  const serverUrl = process.env.LIVEKIT_URL

  if (!apiKey || !apiSecret || !serverUrl) {
    return null
  }

  return { apiKey, apiSecret, serverUrl }
}

export function normalizeLiveKitSegment(value: string | null) {
  return value?.trim().slice(0, 80) ?? ""
}
