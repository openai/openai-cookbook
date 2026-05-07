import {
  classifyLanguageSelection,
  languageMenuText,
  supportedLanguageListText,
} from "./languages.js";

const MAX_LANGUAGE_ATTEMPTS = 3;

const xml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");

export function incomingCallTwiml() {
  return languagePromptTwiml();
}

export function languagePromptTwiml({
  attempt = 0,
  reason = "initial",
  unsupportedLanguage,
} = {}) {
  const nextAttempt = normalizeAttempt(attempt) + 1;
  const action = "/choose-language?attempt=" + nextAttempt;
  const prompt = promptForLanguageAttempt({ reason, unsupportedLanguage });

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    "<Response>",
    '  <Gather input="speech" timeout="10" speechTimeout="auto" action="' +
      xml(action) +
      '" method="POST">',
    "    <Say>" + xml(prompt) + "</Say>",
    "  </Gather>",
    '  <Redirect method="POST">' + xml(action) + "</Redirect>",
    "</Response>",
  ].join("\n");
}

export function rejectedCallerTwiml() {
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    "<Response>",
    "  <Say>This number is not enabled for this demo.</Say>",
    "  <Hangup />",
    "</Response>",
  ].join("\n");
}

export function busyTwiml() {
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    "<Response>",
    "  <Say>The translation demo is currently full. Please try again later.</Say>",
    "  <Hangup />",
    "</Response>",
  ].join("\n");
}

export function chooseLanguageTwiml({
  speechResult,
  host,
  callSid,
  attempt = 0,
}) {
  const selection = classifyLanguageSelection(speechResult);
  if (selection.status !== "supported") {
    const currentAttempt = normalizeAttempt(attempt);
    if (currentAttempt >= MAX_LANGUAGE_ATTEMPTS) {
      return languageFailedTwiml();
    }

    return languagePromptTwiml({
      attempt: currentAttempt,
      reason: selection.status,
      unsupportedLanguage: selection.language,
    });
  }

  const language = selection.language;
  return streamTwiml({
    host,
    callSid,
    language: language.code,
    languageLabel: language.label,
  });
}

export function streamTwiml({ host, callSid, language, languageLabel }) {
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    "<Response>",
    "  <Say>You chose " +
      xml(languageLabel) +
      ". Wait for the other caller, then begin speaking.</Say>",
    "  <Connect>",
    '    <Stream url="wss://' + xml(host) + '/media-stream">',
    '      <Parameter name="callSid" value="' + xml(callSid) + '" />',
    '      <Parameter name="language" value="' + xml(language) + '" />',
    '      <Parameter name="languageLabel" value="' + xml(languageLabel) + '" />',
    "    </Stream>",
    "  </Connect>",
    "</Response>",
  ].join("\n");
}

function promptForLanguageAttempt({ reason, unsupportedLanguage }) {
  if (reason === "unsupported" && unsupportedLanguage) {
    return (
      unsupportedLanguage +
      " is not supported for this demo. Please say one of these languages: " +
      supportedLanguageListText() +
      "."
    );
  }

  if (reason === "missing") {
    return (
      "I didn't catch the language. Please say one of these languages: " +
      supportedLanguageListText() +
      "."
    );
  }

  if (reason === "unknown") {
    return (
      "I didn't hear a supported language. Please say one of these languages: " +
      supportedLanguageListText() +
      "."
    );
  }

  return languageMenuText();
}

function languageFailedTwiml() {
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    "<Response>",
    "  <Say>Sorry, I couldn't confirm a supported language. Please call again and say one of the supported languages.</Say>",
    "  <Hangup />",
    "</Response>",
  ].join("\n");
}

function normalizeAttempt(attempt) {
  const parsed = Number.parseInt(attempt, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}
