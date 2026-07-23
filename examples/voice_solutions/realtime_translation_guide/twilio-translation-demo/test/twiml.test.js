import { describe, expect, it } from "vitest";
import {
  busyTwiml,
  chooseLanguageTwiml,
  incomingCallTwiml,
  languagePromptTwiml,
  rejectedCallerTwiml,
  streamTwiml,
} from "../src/twiml.js";

describe("twiml", () => {
  it("prompts callers to choose their output language by speech", () => {
    const xml = incomingCallTwiml();

    expect(xml).toContain("<Gather");
    expect(xml).toContain('input="speech"');
    expect(xml).not.toContain("dtmf");
    expect(xml).toContain('speechTimeout="auto"');
    expect(xml).toContain('action="/choose-language?attempt=1"');
    expect(xml).toContain("English");
    expect(xml).toContain("Russian");
    expect(xml).not.toContain("Defaulting to Spanish");
  });

  it("connects a caller to a two-way media stream with custom parameters", () => {
    const xml = streamTwiml({
      host: "demo.example.com",
      callSid: "CA123",
      language: "es",
      languageLabel: "Spanish",
    });

    expect(xml).toContain('<Connect>');
    expect(xml).toContain('<Stream url="wss://demo.example.com/media-stream">');
    expect(xml).toContain('<Parameter name="callSid" value="CA123" />');
    expect(xml).toContain('<Parameter name="language" value="es" />');
  });

  it("uses the spoken language when returning stream TwiML", () => {
    const xml = chooseLanguageTwiml({
      speechResult: "I would like Japanese",
      host: "demo.example.com",
      callSid: "CA789",
    });

    expect(xml).toContain("Japanese");
    expect(xml).toContain('<Parameter name="language" value="ja" />');
  });

  it("reprompts when the caller names an unsupported language", () => {
    const xml = chooseLanguageTwiml({
      speechResult: "Swedish",
      host: "demo.example.com",
      callSid: "CA789",
      attempt: "1",
    });

    expect(xml).toContain("<Gather");
    expect(xml).toContain("Swedish is not supported");
    expect(xml).toContain("Please say one of these languages");
    expect(xml).toContain("Vietnamese");
    expect(xml).not.toContain("Arabic");
    expect(xml).not.toContain("<Stream");
  });

  it("reprompts when no language is captured", () => {
    const xml = chooseLanguageTwiml({
      host: "demo.example.com",
      callSid: "CA789",
      attempt: "1",
    });

    expect(xml).toContain("<Gather");
    expect(xml).toContain("I didn&apos;t catch the language");
    expect(xml).not.toContain("Defaulting to Spanish");
  });

  it("hangs up after repeated invalid language attempts", () => {
    const xml = chooseLanguageTwiml({
      speechResult: "Swedish",
      host: "demo.example.com",
      callSid: "CA789",
      attempt: "3",
    });

    expect(xml).toContain("<Hangup");
    expect(xml).toContain("couldn't confirm a supported language");
  });

  it("can render an unsupported-language prompt directly", () => {
    const xml = languagePromptTwiml({
      attempt: 1,
      reason: "unsupported",
      unsupportedLanguage: "Swedish",
    });

    expect(xml).toContain("Swedish is not supported");
    expect(xml).toContain('action="/choose-language?attempt=2"');
  });

  it("rejects callers outside the allow-list", () => {
    const xml = rejectedCallerTwiml();

    expect(xml).toContain("<Hangup");
    expect(xml).toContain("not enabled for this demo");
  });

  it("returns a busy response when the room is at capacity", () => {
    const xml = busyTwiml();

    expect(xml).toContain("<Hangup");
    expect(xml).toContain("demo is currently full");
  });
});
