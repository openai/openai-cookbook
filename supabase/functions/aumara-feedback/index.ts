import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import QRCode from "npm:qrcode@1.5.4";

const VERSION = "2026.08.14.4";
const PROPERTY_ID = 324882;
const BOOKING_BASE = "https://beds24.com/booking2.php";
const PUBLIC_OFFER_BASE = "https://elcidspain.com/aumara/feedback.html";
const ALLOWED_ORIGINS = new Set([
  "https://elcidspain.com",
  "https://www.elcidspain.com",
  "https://elcidspain.github.io",
]);
const ALLOWED_LOCALES = new Set(["en", "es", "it", "ru"]);
const LIKED = new Set([
  "house",
  "comfort",
  "nature",
  "views",
  "privacy",
  "cleanliness",
  "service",
  "location",
]);
const WISHLIST = new Set([
  "house_equipment",
  "landscape_shade",
  "pool_wellness",
  "bar_food",
  "family_facilities",
  "workspace",
  "transport",
  "housekeeping",
]);
const ACTIVITIES = new Set([
  "hiking",
  "cycling",
  "yoga_wellness",
  "cooking",
  "muay_thai",
  "chess",
  "wine_food",
  "family_activities",
  "local_routes",
]);

type CodeRow = {
  discount_code: string;
  guest_first_name: string;
  guest_language: string;
  room_type: string | null;
  stay_arrival: string;
  stay_departure: string;
  discount_percent: string | number;
  min_nights: number;
  transferable: boolean;
  stackable: boolean;
  expires_at: string | null;
  survey_submitted_at: string | null;
  active: boolean;
  beds24_status: "requires_activation" | "active" | "disabled" | "redeemed";
  redemptions_used: number;
  max_redemptions: number;
};

function cors(req: Request): Record<string, string> {
  const origin = req.headers.get("origin") || "";
  const headers: Record<string, string> = {
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "content-type",
    "access-control-max-age": "86400",
    vary: "Origin",
  };
  if (ALLOWED_ORIGINS.has(origin)) headers["access-control-allow-origin"] = origin;
  return headers;
}

function originAllowed(req: Request): boolean {
  const origin = req.headers.get("origin") || "";
  return !origin || ALLOWED_ORIGINS.has(origin);
}

function json(req: Request, data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store, max-age=0",
      "x-content-type-options": "nosniff",
      ...cors(req),
    },
  });
}

function png(req: Request, body: Uint8Array, status = 200): Response {
  return new Response(body, {
    status,
    headers: {
      "content-type": "image/png",
      "content-disposition": "inline",
      "cache-control": "private, no-store, max-age=0",
      "x-content-type-options": "nosniff",
      "x-robots-tag": "noindex, nofollow, noarchive",
      ...cors(req),
    },
  });
}

function env(name: string): string {
  const value = Deno.env.get(name) || "";
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

async function sha256(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function validToken(value: unknown): string | null {
  const token = String(value || "").trim();
  return /^[a-f0-9]{48,128}$/i.test(token) ? token : null;
}

function validCode(value: unknown): string | null {
  const code = String(value || "").trim().toUpperCase();
  return /^[A-Z0-9]{8,32}$/.test(code) ? code : null;
}

function cleanText(value: unknown, max = 1200): string {
  return String(value || "").replace(/\u0000/g, "").trim().slice(0, max);
}

function cleanChoiceArray(value: unknown, allowed: Set<string>, max: number): string[] {
  if (!Array.isArray(value)) return [];
  const result: string[] = [];
  for (const raw of value) {
    const item = String(raw || "").trim();
    if (allowed.has(item) && !result.includes(item)) result.push(item);
    if (result.length >= max) break;
  }
  return result;
}

function isExpired(row: CodeRow): boolean {
  if (!row.expires_at) return false;
  return row.expires_at < new Date().toISOString().slice(0, 10);
}

function offerUrl(code: string): string {
  const url = new URL(PUBLIC_OFFER_BASE);
  url.searchParams.set("code", code);
  return url.toString();
}

function bookingUrl(row: Pick<CodeRow, "discount_code" | "guest_language" | "min_nights">): string {
  const url = new URL(BOOKING_BASE);
  url.searchParams.set("propid", String(PROPERTY_ID));
  url.searchParams.set("voucher", row.discount_code);
  url.searchParams.set("referer", row.discount_code);
  url.searchParams.set("numnight", String(Math.max(5, row.min_nights || 5)));
  url.searchParams.set("lang", ALLOWED_LOCALES.has(row.guest_language) ? row.guest_language : "en");
  url.searchParams.set("mobile", "1");
  return url.toString();
}

async function db(path: string, init: RequestInit = {}): Promise<Response> {
  const supabaseUrl = env("SUPABASE_URL");
  const serviceKey = env("SUPABASE_SERVICE_ROLE_KEY");
  const headers = new Headers(init.headers || {});
  headers.set("apikey", serviceKey);
  headers.set("authorization", `Bearer ${serviceKey}`);
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  return await fetch(`${supabaseUrl}${path}`, { ...init, headers });
}

const CODE_SELECT = [
  "discount_code",
  "guest_first_name",
  "guest_language",
  "room_type",
  "stay_arrival",
  "stay_departure",
  "discount_percent",
  "min_nights",
  "transferable",
  "stackable",
  "expires_at",
  "survey_submitted_at",
  "active",
  "beds24_status",
  "redemptions_used",
  "max_redemptions",
].join(",");

async function oneCode(filter: string): Promise<CodeRow | null> {
  const response = await db(`/rest/v1/aumara_feedback_codes?select=${encodeURIComponent(CODE_SELECT)}&${filter}&limit=1`, {
    method: "GET",
  });
  if (!response.ok) throw new Error(`Database lookup failed: HTTP ${response.status}`);
  const rows = (await response.json()) as CodeRow[];
  return rows[0] || null;
}

async function codeByToken(token: string): Promise<CodeRow | null> {
  const hash = await sha256(token);
  return await oneCode(`survey_token_hash=eq.${encodeURIComponent(hash)}`);
}

async function codeByCode(code: string): Promise<CodeRow | null> {
  return await oneCode(`discount_code=eq.${encodeURIComponent(code)}`);
}

async function logEvent(code: string, eventType: string, metadata: Record<string, unknown> = {}): Promise<void> {
  try {
    await db("/rest/v1/aumara_feedback_events", {
      method: "POST",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify({ discount_code: code, event_type: eventType, metadata }),
    });
  } catch {
    // Engagement logging must never block the guest flow.
  }
}

function safeProfile(row: CodeRow) {
  const completed = Boolean(row.survey_submitted_at);
  const readyForBooking = row.beds24_status === "active" && row.active && !isExpired(row) && row.redemptions_used < row.max_redemptions;
  return {
    guestFirstName: row.guest_first_name,
    locale: row.guest_language,
    roomType: row.room_type,
    stayArrival: row.stay_arrival,
    stayDeparture: row.stay_departure,
    surveySubmitted: completed,
    reward: {
      discountPercent: Number(row.discount_percent),
      minNights: row.min_nights,
      transferable: row.transferable,
      stackable: row.stackable,
      expiresAt: row.expires_at,
      readyForBooking,
    },
    ...(completed
      ? {
          discountCode: row.discount_code,
          bookingUrl: readyForBooking ? bookingUrl(row) : null,
        }
      : {}),
  };
}

async function handleProfile(req: Request): Promise<Response> {
  const length = Number(req.headers.get("content-length") || 0);
  if (length > 4096) return json(req, { ok: false, error: "Payload too large" }, 413);
  const body = await req.json();
  const token = validToken(body?.token);
  if (!token) return json(req, { ok: false, error: "Invalid survey link" }, 400);
  const row = await codeByToken(token);
  if (!row || !row.active || isExpired(row)) return json(req, { ok: false, error: "Survey link unavailable" }, 404);
  await logEvent(row.discount_code, "survey_opened", { version: VERSION });
  return json(req, { ok: true, profile: safeProfile(row) });
}

async function handleOffer(req: Request, url: URL): Promise<Response> {
  const code = validCode(url.searchParams.get("code"));
  if (!code) return json(req, { ok: false, error: "Invalid discount code" }, 400);
  const row = await codeByCode(code);
  if (!row || !row.survey_submitted_at || !row.active || isExpired(row) || row.redemptions_used >= row.max_redemptions) {
    return json(req, { ok: false, error: "Discount code unavailable" }, 404);
  }
  const readyForBooking = row.beds24_status === "active";
  return json(req, {
    ok: true,
    offer: {
      discountCode: row.discount_code,
      locale: row.guest_language,
      discountPercent: Number(row.discount_percent),
      minNights: row.min_nights,
      transferable: row.transferable,
      stackable: row.stackable,
      expiresAt: row.expires_at,
      readyForBooking,
      bookingUrl: readyForBooking ? bookingUrl(row) : null,
    },
  });
}

async function handleQr(req: Request, url: URL): Promise<Response> {
  const code = validCode(url.searchParams.get("code"));
  if (!code) return json(req, { ok: false, error: "Invalid discount code" }, 400);
  const row = await codeByCode(code);
  if (!row || !row.survey_submitted_at || !row.active || isExpired(row) || row.redemptions_used >= row.max_redemptions) {
    return json(req, { ok: false, error: "Discount code unavailable" }, 404);
  }
  const dataUrl = await QRCode.toDataURL(offerUrl(row.discount_code), {
    type: "image/png",
    errorCorrectionLevel: "M",
    margin: 2,
    width: 256,
    color: { dark: "#213329", light: "#fffaf1" },
  });
  const encoded = dataUrl.slice(dataUrl.indexOf(",") + 1);
  const binary = atob(encoded);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return png(req, bytes);
}

async function handleSubmit(req: Request): Promise<Response> {
  const length = Number(req.headers.get("content-length") || 0);
  if (length > 32768) return json(req, { ok: false, error: "Payload too large" }, 413);
  const body = await req.json();
  const token = validToken(body?.token);
  if (!token) return json(req, { ok: false, error: "Invalid survey link" }, 400);

  const overallRating = Number(body?.overallRating);
  const recommendScore = Number(body?.recommendScore);
  if (!Number.isInteger(overallRating) || overallRating < 1 || overallRating > 5) {
    return json(req, { ok: false, error: "Overall rating is required" }, 400);
  }
  if (!Number.isInteger(recommendScore) || recommendScore < 0 || recommendScore > 10) {
    return json(req, { ok: false, error: "Recommendation score is required" }, 400);
  }

  const locale = ALLOWED_LOCALES.has(String(body?.locale || "")) ? String(body.locale) : "en";
  const tokenHash = await sha256(token);
  const response = await db("/rest/v1/rpc/aumara_submit_feedback", {
    method: "POST",
    body: JSON.stringify({
      p_token_hash: tokenHash,
      p_overall_rating: overallRating,
      p_recommend_score: recommendScore,
      p_liked: cleanChoiceArray(body?.liked, LIKED, 8),
      p_improvement_text: cleanText(body?.improvementText),
      p_add_wishlist: cleanChoiceArray(body?.addWishlist, WISHLIST, 8),
      p_activity_interests: cleanChoiceArray(body?.activityInterests, ACTIVITIES, 10),
      p_final_comment: cleanText(body?.finalComment),
      p_testimonial_consent: body?.testimonialConsent === true,
      p_locale: locale,
    }),
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = String(payload?.message || payload?.error || "Feedback submission failed");
    const unavailable = message.includes("invalid_or_inactive_token") || message.includes("expired_token");
    return json(req, { ok: false, error: unavailable ? "Survey link unavailable" : "Feedback submission failed" }, unavailable ? 404 : 400);
  }

  const result = Array.isArray(payload) ? payload[0] : payload;
  if (!result?.discount_code) return json(req, { ok: false, error: "Feedback submission failed" }, 500);
  const row = await codeByCode(result.discount_code);
  if (!row) return json(req, { ok: false, error: "Discount record unavailable" }, 500);
  return json(req, { ok: true, reward: safeProfile(row) });
}

async function handleBook(req: Request, url: URL): Promise<Response> {
  const code = validCode(url.searchParams.get("code"));
  if (!code) return json(req, { ok: false, error: "Invalid discount code" }, 400);
  const row = await codeByCode(code);
  const usable = row && row.survey_submitted_at && row.active && !isExpired(row) && row.redemptions_used < row.max_redemptions;
  if (!usable) return json(req, { ok: false, error: "Discount code unavailable" }, 404);
  if (row.beds24_status !== "active") return json(req, { ok: false, error: "Discount code is not yet activated" }, 409);
  await logEvent(row.discount_code, "booking_link_opened", { version: VERSION });
  return new Response(null, {
    status: 302,
    headers: {
      location: bookingUrl(row),
      "cache-control": "no-store",
      ...cors(req),
    },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(req) });
  if (!originAllowed(req)) return json(req, { ok: false, error: "Origin not allowed" }, 403);

  try {
    const url = new URL(req.url);
    const action = String(url.searchParams.get("action") || "health").toLowerCase();

    if (req.method === "GET" && action === "health") {
      return json(req, { ok: true, api: "aumara-feedback", version: VERSION });
    }
    if (req.method === "POST" && action === "profile") return await handleProfile(req);
    if (req.method === "GET" && action === "offer") return await handleOffer(req, url);
    if (req.method === "GET" && action === "qr") return await handleQr(req, url);
    if (req.method === "GET" && action === "book") return await handleBook(req, url);
    if (req.method === "POST" && action === "submit") return await handleSubmit(req);

    return json(req, { ok: false, error: "Method or action not allowed" }, 405);
  } catch (error) {
    console.error("aumara-feedback", error);
    return json(req, { ok: false, error: "Service temporarily unavailable" }, 500);
  }
});
