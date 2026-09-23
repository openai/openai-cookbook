export const DEFAULT_TRANSLATED_MIX = 85;

export function clampTranslatedMix(value) {
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_TRANSLATED_MIX;
  }
  return Math.min(100, Math.max(0, parsed));
}

export function buildAudioMixState(value) {
  const translatedPercent = clampTranslatedMix(value);
  const originalPercent = 100 - translatedPercent;

  return {
    translatedPercent,
    originalPercent,
    translatedVolume: translatedPercent / 100,
    originalVolume: originalPercent / 100,
    valueLabel: `${translatedPercent}% translated`,
    translatedLabel: `Translated ${translatedPercent}%`,
    originalLabel: `Original ${originalPercent}%`,
  };
}
