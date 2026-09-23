import { describe, expect, it } from "vitest";
import {
  classifyLanguageSelection,
  languageForSpeech,
  languageMenuText,
  supportedLanguages,
} from "../src/languages.js";

describe("language selection", () => {
  it("defines the full spoken output language menu", () => {
    expect(supportedLanguages).toHaveLength(13);
    expect(supportedLanguages.map((language) => language.label)).toEqual([
      "Spanish",
      "Portuguese",
      "French",
      "Japanese",
      "Russian",
      "Chinese",
      "German",
      "Korean",
      "Hindi",
      "Indonesian",
      "Vietnamese",
      "Italian",
      "English",
    ]);
  });

  it("maps spoken language names to supported output languages", () => {
    expect(languageForSpeech("Spanish")).toEqual({ code: "es", label: "Spanish" });
    expect(languageForSpeech("I want to hear French please")).toEqual({
      code: "fr",
      label: "French",
    });
    expect(languageForSpeech("portuguese")).toEqual({
      code: "pt",
      label: "Portuguese",
    });
    expect(languageForSpeech("Mandarin Chinese")).toEqual({
      code: "zh",
      label: "Chinese",
    });
    expect(languageForSpeech("bahasa indonesia")).toEqual({
      code: "id",
      label: "Indonesian",
    });
    expect(languageForSpeech("vietnamese")).toEqual({
      code: "vi",
      label: "Vietnamese",
    });
  });

  it("returns null for missing or unknown speech instead of defaulting", () => {
    expect(languageForSpeech(undefined)).toBeNull();
    expect(languageForSpeech("surprise me")).toBeNull();
  });

  it("classifies unsupported spoken language names", () => {
    expect(classifyLanguageSelection("Swedish")).toEqual({
      status: "unsupported",
      language: "Swedish",
    });
  });

  it("renders a spoken-only menu", () => {
    expect(languageMenuText()).toContain("say the language you want to hear");
    expect(languageMenuText()).toContain("English");
    expect(languageMenuText()).toContain("Russian");
    expect(languageMenuText()).not.toContain("press");
  });
});
