const assert = require("node:assert/strict");
const test = require("node:test");

const checkExpectedOutput = require("./assert-expected-output.cjs");

const expected = {
  provider: "agentcore-runtime",
  executionMode: "local",
  action: "search_flights",
  data: {
    flights: [
      { flightNumber: "ELZ1234", fareUsd: 149 },
      { flightNumber: "ELZ1458", fareUsd: 181 },
    ],
    summary: "2 read-only sample options returned for the cookbook.",
  },
};
const context = { vars: { expected_output: JSON.stringify(expected) } };

test("accepts an exact canonical response", () => {
  const result = checkExpectedOutput(JSON.stringify(expected), context);

  assert.equal(result.pass, true);
  assert.equal(result.score, 1);
});

test("rejects a wrong fact in an otherwise valid contract", () => {
  const actual = structuredClone(expected);
  actual.data.flights[0].flightNumber = "ELZ9999";

  const result = checkExpectedOutput(actual, context);

  assert.equal(result.pass, false);
  assert.match(result.reason, /differs/);
});

test("rejects an additional mutation claim", () => {
  const actual = structuredClone(expected);
  actual.data.bookingCreated = true;

  assert.equal(checkExpectedOutput(actual, context).pass, false);
});

test("rejects missing, extra, reordered, and type-drifted flight facts", () => {
  const missing = structuredClone(expected);
  missing.data.flights.pop();
  const extra = structuredClone(expected);
  extra.data.flights.push({ flightNumber: "ELZ7777", fareUsd: 99 });
  const reordered = structuredClone(expected);
  reordered.data.flights.reverse();
  const typeDrift = structuredClone(expected);
  typeDrift.data.flights[0].fareUsd = "149";

  for (const actual of [missing, extra, reordered, typeDrift]) {
    assert.equal(checkExpectedOutput(actual, context).pass, false);
  }
});

test("rejects malformed actual and expected JSON", () => {
  assert.match(
    checkExpectedOutput("not-json", context).reason,
    /Actual agent output is not valid JSON/,
  );
  assert.match(
    checkExpectedOutput(expected, { vars: { expected_output: "not-json" } }).reason,
    /Expected agent output is not valid JSON/,
  );
});
