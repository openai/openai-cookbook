// A compact 0–600 dial gives typical output rates more visual range.
// Only the dial saturates; the numeric reading remains uncapped.
export const BUILD_SPEEDOMETER_MAX_TPS = 600;

export function speedometerPosition(rate: number | null) {
  const fraction = Math.min(1, Math.max(0, rate !== null && Number.isFinite(rate) ? rate / BUILD_SPEEDOMETER_MAX_TPS : 0));
  return {
    fraction,
    rotation: -90 + fraction * 180,
    dashOffset: 100 * (1 - fraction),
  };
}
