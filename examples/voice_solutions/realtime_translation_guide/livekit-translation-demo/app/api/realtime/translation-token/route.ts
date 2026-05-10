import { NextResponse } from "next/server"

import {
  buildTranslationClientSecretRequest,
  normalizeTranslationLanguage,
} from "@/lib/realtime-translation-config"

type TranslationTokenRequest = {
  language?: string
  inputTranscriptionEnabled?: boolean
  noiseReductionEnabled?: boolean
}

type ClientSecretResponse = {
  value?: string
  expires_at?: number
  client_secret?: {
    value?: string
    expires_at?: number
  }
}

export async function POST(request: Request) {
  const apiKey = process.env.OPENAI_API_KEY

  if (!apiKey) {
    return new NextResponse("Missing OPENAI_API_KEY", { status: 500 })
  }

  let payload: TranslationTokenRequest
  try {
    payload = (await request.json()) as TranslationTokenRequest
  } catch {
    return new NextResponse("Invalid JSON body", { status: 400 })
  }

  let language: string
  try {
    language = normalizeTranslationLanguage(payload.language || "es")
  } catch (error) {
    return new NextResponse(
      error instanceof Error ? error.message : "Unsupported translation language",
      { status: 400 }
    )
  }

  const translationRequest = buildTranslationClientSecretRequest({
    apiKey,
    language,
    inputTranscriptionEnabled: !!payload.inputTranscriptionEnabled,
    noiseReductionEnabled: !!payload.noiseReductionEnabled,
    model: process.env.OPENAI_TRANSLATION_MODEL,
  })

  const response = await fetch(translationRequest.url, translationRequest.init)

  if (!response.ok) {
    return new NextResponse(await response.text(), {
      status: response.status,
    })
  }

  const data = (await response.json()) as ClientSecretResponse
  const clientSecret = data.value ?? data.client_secret?.value

  if (!clientSecret) {
    return new NextResponse(
      "Realtime translation client secret response was missing value",
      { status: 502 }
    )
  }

  return NextResponse.json({
    clientSecret,
    expiresAt: data.expires_at ?? data.client_secret?.expires_at ?? null,
  })
}
