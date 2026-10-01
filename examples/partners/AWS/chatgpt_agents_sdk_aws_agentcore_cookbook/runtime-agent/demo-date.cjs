const DEMO_TRAVEL_DATE_ENV = "COOKBOOK_DEMO_TRAVEL_DATE";
const DEMO_TRAVEL_DATE_TOKEN = "{{COOKBOOK_DEMO_TRAVEL_DATE}}";
const DEFAULT_LEAD_DAYS = 45;

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function demoTravelDate({ env = process.env, now = new Date() } = {}) {
  const today = new Date(Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate(),
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

function materializeDemoDate(value, travelDate) {
  if (typeof value === "string") {
    return value.replaceAll(DEMO_TRAVEL_DATE_TOKEN, travelDate);
  }
  if (Array.isArray(value)) {
    return value.map((item) => materializeDemoDate(item, travelDate));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, materializeDemoDate(item, travelDate)]),
    );
  }
  return value;
}

module.exports = {
  DEFAULT_LEAD_DAYS,
  DEMO_TRAVEL_DATE_ENV,
  DEMO_TRAVEL_DATE_TOKEN,
  demoTravelDate,
  materializeDemoDate,
};
