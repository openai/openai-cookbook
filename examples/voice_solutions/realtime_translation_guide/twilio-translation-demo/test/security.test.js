import { createHmac } from "node:crypto";
import { describe, expect, it } from "vitest";
import {
  isAllowedCaller,
  publicWebhookUrl,
  verifyTwilioSignature,
} from "../src/security.js";

function sign(url, params, authToken) {
  const data =
    url +
    Object.keys(params)
      .sort()
      .map((key) => `${key}${params[key]}`)
      .join("");

  return createHmac("sha1", authToken).update(data).digest("base64");
}

describe("Twilio request security", () => {
  it("validates Twilio signatures for form webhooks", () => {
    const url = "https://demo.example.com/incoming-call";
    const params = { CallSid: "CA123", From: "+15551234567", To: "+15557654321" };
    const authToken = "test-token";
    const signature = sign(url, params, authToken);

    expect(
      verifyTwilioSignature({
        authToken,
        params,
        signature,
        url,
      }),
    ).toBe(true);
  });

  it("rejects invalid Twilio signatures", () => {
    expect(
      verifyTwilioSignature({
        authToken: "test-token",
        params: { CallSid: "CA123" },
        signature: "bad-signature",
        url: "https://demo.example.com/incoming-call",
      }),
    ).toBe(false);
  });

  it("allows callers when no allow-list is configured", () => {
    expect(isAllowedCaller("+15551234567", undefined)).toBe(true);
  });

  it("requires exact caller matches when an allow-list is configured", () => {
    const allowList = "+15551234567, +15557654321";

    expect(isAllowedCaller("+15551234567", allowList)).toBe(true);
    expect(isAllowedCaller("+15550000000", allowList)).toBe(false);
  });

  it("builds public webhook URLs from PUBLIC_URL so signature validation survives proxies", () => {
    const request = {
      url: "/choose-language?foo=bar",
      headers: { host: "internal.local" },
    };

    expect(publicWebhookUrl(request, { PUBLIC_URL: "https://demo.example.com" })).toBe(
      "https://demo.example.com/choose-language?foo=bar",
    );
  });
});
