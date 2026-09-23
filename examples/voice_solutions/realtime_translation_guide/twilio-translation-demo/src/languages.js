export const supportedLanguages = [
  { code: "es", label: "Spanish", aliases: ["spanish"] },
  { code: "pt", label: "Portuguese", aliases: ["portuguese"] },
  { code: "fr", label: "French", aliases: ["french"] },
  { code: "ja", label: "Japanese", aliases: ["japanese"] },
  { code: "ru", label: "Russian", aliases: ["russian"] },
  {
    code: "zh",
    label: "Chinese",
    aliases: ["chinese", "mandarin", "mandarin chinese"],
  },
  { code: "de", label: "German", aliases: ["german"] },
  { code: "ko", label: "Korean", aliases: ["korean"] },
  { code: "hi", label: "Hindi", aliases: ["hindi"] },
  {
    code: "id",
    label: "Indonesian",
    aliases: ["indonesian", "bahasa indonesia"],
  },
  { code: "vi", label: "Vietnamese", aliases: ["vietnamese"] },
  { code: "it", label: "Italian", aliases: ["italian"] },
  { code: "en", label: "English", aliases: ["english"] },
];

const unsupportedLanguageNames = [
  "Afrikaans",
  "Arabic",
  "Armenian",
  "Azerbaijani",
  "Bengali",
  "Bulgarian",
  "Catalan",
  "Croatian",
  "Czech",
  "Danish",
  "Dutch",
  "Finnish",
  "Greek",
  "Hebrew",
  "Hungarian",
  "Malay",
  "Norwegian",
  "Persian",
  "Polish",
  "Romanian",
  "Swahili",
  "Swedish",
  "Tagalog",
  "Tamil",
  "Thai",
  "Turkish",
  "Ukrainian",
  "Urdu",
];

export function languageForDigit(digit) {
  const index = Number.parseInt(digit, 10) - 1;
  return publicLanguage(supportedLanguages[index]);
}

export function languageForSpeech(speech) {
  const selection = classifyLanguageSelection(speech);
  return selection.status === "supported" ? selection.language : null;
}

export function classifyLanguageSelection(speech) {
  const normalized = normalizeSpeech(speech);
  if (!normalized) {
    return { status: "missing" };
  }

  const match = supportedLanguages.find((language) =>
    language.aliases.some((alias) => includesPhrase(normalized, alias)),
  );
  if (match) {
    return { status: "supported", language: publicLanguage(match) };
  }

  const unsupported = unsupportedLanguageNames.find((language) =>
    includesPhrase(normalized, language),
  );
  if (unsupported) {
    return { status: "unsupported", language: unsupported };
  }

  return { status: "unknown" };
}

export function languageLabelForCode(code) {
  return supportedLanguages.find((language) => language.code === code)?.label ?? code;
}

export function languageMenuText() {
  return (
    "Please say the language you want to hear. Supported languages are " +
    supportedLanguageListText() +
    "."
  );
}

export function supportedLanguageListText() {
  const labels = supportedLanguages.map((language) => language.label);
  return labels.slice(0, -1).join(", ") + ", or " + labels[labels.length - 1];
}

function normalizeSpeech(speech) {
  return String(speech ?? "")
    .toLowerCase()
    .replace(/[^a-z\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function includesPhrase(normalized, phrase) {
  const normalizedPhrase = normalizeSpeech(phrase);
  return new RegExp("(^|\\s)" + escapeRegExp(normalizedPhrase) + "($|\\s)").test(
    normalized,
  );
}

function publicLanguage(language) {
  return language ? { code: language.code, label: language.label } : null;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^$(){}|[\]\\]/g, "\\$&");
}
