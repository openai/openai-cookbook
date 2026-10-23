const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { demoTravelDate } = require("../demo-date.cjs");

const {
  loadAgentEvaluationCases,
  parseCaseIds,
} = require("./agent-evaluation-cases.cjs");

test("demo date defaults to 45 UTC days ahead and validates overrides", () => {
  const now = new Date("2030-01-10T22:00:00Z");
  assert.equal(demoTravelDate({ env: {}, now }), "2030-02-24");
  assert.equal(
    demoTravelDate({ env: { COOKBOOK_DEMO_TRAVEL_DATE: "2030-03-01" }, now }),
    "2030-03-01",
  );
  assert.throws(
    () => demoTravelDate({ env: { COOKBOOK_DEMO_TRAVEL_DATE: "2030-01-10" }, now }),
    /must be later than today/,
  );
});

function withFixture(records, callback) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "agent-evaluation-cases-"));
  const fixturePath = path.join(directory, "cases.jsonl");
  fs.writeFileSync(
    fixturePath,
    `${records.map((record) => JSON.stringify(record)).join("\n")}\n`,
    "utf8",
  );
  try {
    callback(fixturePath);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

function runnableRecord(overrides = {}) {
  return {
    case_id: "upcoming-status",
    expected_provider: "agentcore-runtime",
    expected_execution_mode: "local",
    expected_action: "get_upcoming_status",
    output: {
      provider: "agentcore-runtime",
      executionMode: "local",
      action: "get_upcoming_status",
      data: { flight: { flightNumber: "ELZ4321", status: "ON_TIME" } },
    },
    aws_evaluation: {
      request: { action: "get_upcoming_status" },
      assertions: ["The result is read-only."],
      expected_trajectory: ["get_mock_upcoming_eliza_airlines_trip"],
    },
    ...overrides,
  };
}

test("selects only the three tagged canonical cases", () => {
  const records = loadAgentEvaluationCases();

  assert.deepEqual(
    records.map((record) => record.case_id),
    ["search-flights", "upcoming-status", "live-status-on-time"],
  );
  assert.ok(records.every((record) => record.expected_contract_valid !== false));
  assert.ok(records.every((record) => record.expected_execution_mode === "local"));
});

test("canonical cases preserve the walkthrough flight and date", () => {
  const [searchCase, upcomingCase, liveCase] = loadAgentEvaluationCases();
  const firstFlight = searchCase.output.data.flights[0];
  const expectedTravelDate = demoTravelDate();

  assert.equal(searchCase.aws_evaluation.request.travel_date, expectedTravelDate);
  assert.equal(firstFlight.travelDate, searchCase.aws_evaluation.request.travel_date);
  assert.equal(upcomingCase.output.data.flight.travelDate, expectedTravelDate);
  assert.deepEqual(liveCase.aws_evaluation.request, {
    action: "get_live_status",
    flight_number: firstFlight.flightNumber,
    origin: firstFlight.origin,
    destination: firstFlight.destination,
    travel_date: firstFlight.travelDate,
  });
  assert.equal(liveCase.output.data.flight.flightNumber, firstFlight.flightNumber);
  assert.equal(liveCase.output.data.flight.travelDate, firstFlight.travelDate);
});

test("supports an explicit case subset without duplicates", () => {
  assert.deepEqual(
    parseCaseIds("live-status-on-time, search-flights,live-status-on-time"),
    ["live-status-on-time", "search-flights"],
  );
  assert.deepEqual(
    loadAgentEvaluationCases({ caseIds: ["live-status-on-time"] })
      .map((record) => record.case_id),
    ["live-status-on-time"],
  );
});

test("rejects an unknown runnable case ID", () => {
  assert.throws(
    () => loadAgentEvaluationCases({ caseIds: ["does-not-exist"] }),
    /Unknown runnable evaluation case IDs/,
  );
});

test("rejects duplicate case IDs", () => {
  withFixture([runnableRecord(), runnableRecord()], (fixturePath) => {
    assert.throws(
      () => loadAgentEvaluationCases({ fixturePath }),
      /duplicates case_id upcoming-status/,
    );
  });
});

test("rejects malformed IDs and non-boolean validity flags", () => {
  withFixture([runnableRecord({ case_id: "   " })], (fixturePath) => {
    assert.throws(
      () => loadAgentEvaluationCases({ fixturePath }),
      /invalid case_id/,
    );
  });
  withFixture([
    runnableRecord({ expected_contract_valid: "false" }),
  ], (fixturePath) => {
    assert.throws(
      () => loadAgentEvaluationCases({ fixturePath }),
      /expected_contract_valid must be a boolean/,
    );
  });
});

test("rejects an expected-invalid runnable case", () => {
  withFixture([runnableRecord({ expected_contract_valid: false })], (fixturePath) => {
    assert.throws(
      () => loadAgentEvaluationCases({ fixturePath }),
      /cannot be both runnable and expected-invalid/,
    );
  });
});

test("rejects a runnable canonical output without object-shaped data", () => {
  withFixture([
    runnableRecord({
      output: {
        provider: "agentcore-runtime",
        executionMode: "local",
        action: "get_upcoming_status",
      },
    }),
  ], (fixturePath) => {
    assert.throws(
      () => loadAgentEvaluationCases({ fixturePath }),
      /canonical output\.data must be a JSON object/,
    );
  });
});

test("rejects missing or non-local execution-mode metadata", () => {
  withFixture([
    runnableRecord({ expected_execution_mode: undefined }),
  ], (fixturePath) => {
    assert.throws(
      () => loadAgentEvaluationCases({ fixturePath }),
      /invalid expected_execution_mode/,
    );
  });
  withFixture([
    runnableRecord({
      expected_execution_mode: "deployed",
      output: {
        ...runnableRecord().output,
        executionMode: "deployed",
      },
    }),
  ], (fixturePath) => {
    assert.throws(
      () => loadAgentEvaluationCases({ fixturePath }),
      /must use local mode/,
    );
  });
});

test("rejects request and expected action drift", () => {
  withFixture([
    runnableRecord({
      aws_evaluation: {
        request: { action: "get_live_status", flight_number: "ELZ1628" },
      },
    }),
  ], (fixturePath) => {
    assert.throws(
      () => loadAgentEvaluationCases({ fixturePath }),
      /request and expected actions do not match/,
    );
  });
});
