const DEMO_TRAVEL_DATE_ENV = "COOKBOOK_DEMO_TRAVEL_DATE";
const DEFAULT_LEAD_DAYS = 45;

function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

export function demoTravelDate(
  env: NodeJS.ProcessEnv = process.env,
  now: Date = new Date()
): string {
  const today = new Date(Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate()
  ));
  const configured = env[DEMO_TRAVEL_DATE_ENV]?.trim();
  if (!configured) {
    today.setUTCDate(today.getUTCDate() + DEFAULT_LEAD_DAYS);
    return isoDate(today);
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(configured)) {
    throw new Error(`${DEMO_TRAVEL_DATE_ENV} must be an ISO date (YYYY-MM-DD)`);
  }
  const resolved = new Date(`${configured}T00:00:00Z`);
  if (Number.isNaN(resolved.valueOf()) || isoDate(resolved) !== configured) {
    throw new Error(`${DEMO_TRAVEL_DATE_ENV} must be an ISO date (YYYY-MM-DD)`);
  }
  if (resolved <= today) {
    throw new Error(`${DEMO_TRAVEL_DATE_ENV} must be later than today`);
  }
  return configured;
}
