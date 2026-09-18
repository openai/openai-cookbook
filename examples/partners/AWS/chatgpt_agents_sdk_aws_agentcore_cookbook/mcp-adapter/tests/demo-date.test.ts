import { describe, expect, it } from "vitest";

import { demoTravelDate } from "../demo-date.js";

const NOW = new Date("2030-01-10T22:00:00Z");

describe("demo travel date", () => {
  it("defaults to a UTC date 45 days in the future", () => {
    expect(demoTravelDate({}, NOW)).toBe("2030-02-24");
  });

  it("accepts a future deterministic override", () => {
    expect(demoTravelDate({ COOKBOOK_DEMO_TRAVEL_DATE: "2030-03-01" }, NOW))
      .toBe("2030-03-01");
  });

  it.each(["not-a-date", "2030-02-30", "2030-01-10", "2029-12-31"])(
    "rejects an invalid or non-future override: %s",
    (value) => {
      expect(() => demoTravelDate({ COOKBOOK_DEMO_TRAVEL_DATE: value }, NOW))
        .toThrow(/must be an ISO date|must be later than today/);
    }
  );
});
