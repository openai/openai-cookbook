const assert = require("node:assert/strict");
const test = require("node:test");

const checkRuntimeContract = require("./assert-runtime-contract.cjs");

const context = {
  vars: {
    expected_provider: "agentcore-runtime",
    expected_execution_mode: "local",
    expected_action: "get_upcoming_status",
    expected_contract_valid: true,
  },
};

test("accepts a matching upcoming-status result", () => {
  const result = checkRuntimeContract(JSON.stringify({
    provider: "agentcore-runtime",
    executionMode: "local",
    action: "get_upcoming_status",
    data: {
      flight: {
        flightNumber: "ELZ4321",
        origin: "DAL",
        destination: "MDW",
        travelDate: "2099-09-21",
        status: "ON_TIME",
        summary: "Mock upcoming trip is on time.",
      },
    },
  }), context);

  assert.equal(result.pass, true);
  assert.equal(result.score, 1);
});

test("rejects a wrong action", () => {
  const result = checkRuntimeContract(JSON.stringify({
    provider: "agentcore-runtime",
    executionMode: "local",
    action: "search_flights",
    data: { flight: { flightNumber: "ELZ4321", status: "ON_TIME" } },
  }), context);

  assert.equal(result.pass, false);
  assert.match(result.reason, /mismatch/);
});

test("rejects malformed JSON", () => {
  const result = checkRuntimeContract("not-json", context);

  assert.equal(result.pass, false);
  assert.match(result.reason, /not valid JSON/);
});

test("passes when an invalid provider is rejected as expected", () => {
  const result = checkRuntimeContract(JSON.stringify({
    provider: "mock-runtime",
    executionMode: "local",
    action: "get_upcoming_status",
    data: { flight: { flightNumber: "ELZ4321", status: "ON_TIME" } },
  }), {
    vars: { ...context.vars, expected_contract_valid: false },
  });

  assert.equal(result.pass, true);
  assert.equal(result.score, 1);
  assert.match(result.reason, /Rejected as expected/);
});

test("fails when an expected-invalid result satisfies the contract", () => {
  const result = checkRuntimeContract(JSON.stringify({
    provider: "agentcore-runtime",
    executionMode: "local",
    action: "get_upcoming_status",
    data: {
      flight: {
        flightNumber: "ELZ4321",
        origin: "DAL",
        destination: "MDW",
        travelDate: "2099-09-21",
        status: "DELAYED",
        summary: "Mock upcoming trip is delayed.",
      },
    },
  }), {
    vars: { ...context.vars, expected_contract_valid: false },
  });

  assert.equal(result.pass, false);
  assert.match(result.reason, /expected.*rejected/i);
});

test("accepts a complete live-status response regardless of status value", () => {
  const result = checkRuntimeContract(JSON.stringify({
    provider: "agentcore-runtime",
    executionMode: "local",
    action: "get_live_status",
    data: {
      flight: {
        flightNumber: "ELZ1628",
        origin: "DAL",
        destination: "MDW",
        travelDate: "2099-09-21",
        status: "CANCELLED",
        summary: "Mock live status is cancelled.",
      },
    },
  }), {
    vars: { ...context.vars, expected_action: "get_live_status" },
  });

  assert.equal(result.pass, true);
  assert.equal(result.score, 1);
});

test("rejects a search flight that does not match the adapter schema", () => {
  const result = checkRuntimeContract(JSON.stringify({
    provider: "agentcore-runtime",
    executionMode: "local",
    action: "search_flights",
    data: {
      flights: [{
        flightNumber: "ELZ2143",
        origin: "MDW",
        destination: "DAL",
        travelDate: "2099-09-21",
      }],
      summary: "One return flight option",
    },
  }), {
    vars: { ...context.vars, expected_action: "search_flights" },
  });

  assert.equal(result.pass, false);
  assert.match(result.reason, /strict Runtime response schema/);
});

test("accepts an empty search result when the strict response schema is complete", () => {
  const result = checkRuntimeContract(JSON.stringify({
    provider: "agentcore-runtime",
    executionMode: "local",
    action: "search_flights",
    data: {
      flights: [],
      summary: "No flight options matched.",
    },
  }), {
    vars: { ...context.vars, expected_action: "search_flights" },
  });

  assert.equal(result.pass, true);
  assert.equal(result.score, 1);
});

test("rejects an otherwise complete search result without a travel date", () => {
  const result = checkRuntimeContract(JSON.stringify({
    provider: "agentcore-runtime",
    executionMode: "local",
    action: "search_flights",
    data: {
      flights: [{
        flightNumber: "ELZ1234",
        origin: "DAL",
        destination: "MDW",
        departTime: "08:15",
        arriveTime: "10:05",
        fareUsd: 149,
      }],
      summary: "One read-only sample option.",
    },
  }), {
    vars: { ...context.vars, expected_action: "search_flights" },
  });

  assert.equal(result.pass, false);
  assert.match(result.reason, /strict Runtime response schema/);
});

test("rejects a non-AgentCore provider even when fixture metadata drifts with it", () => {
  const result = checkRuntimeContract(JSON.stringify({
    provider: "mock-runtime",
    executionMode: "local",
    action: "search_flights",
    data: {
      flights: [],
      summary: "No flight options matched.",
    },
  }), {
    vars: {
      ...context.vars,
      expected_provider: "mock-runtime",
      expected_action: "search_flights",
    },
  });

  assert.equal(result.pass, false);
  assert.match(result.reason, /strict Runtime response schema/);
});

test("rejects a missing or incorrect execution mode", () => {
  const output = {
    provider: "agentcore-runtime",
    action: "get_upcoming_status",
    data: {
      flight: {
        flightNumber: "ELZ4321",
        origin: "DAL",
        destination: "MDW",
        travelDate: "2099-09-21",
        status: "ON_TIME",
        summary: "Mock upcoming trip is on time.",
      },
    },
  };

  assert.equal(checkRuntimeContract(output, context).pass, false);
  assert.equal(
    checkRuntimeContract({ ...output, executionMode: "deployed" }, context).pass,
    false,
  );
  assert.equal(
    checkRuntimeContract({ ...output, executionMode: "local" }, context).pass,
    true,
  );
});

test("rejects an unknown execution mode even when fixture metadata drifts with it", () => {
  const result = checkRuntimeContract({
    provider: "agentcore-runtime",
    executionMode: "remote",
    action: "get_upcoming_status",
    data: {
      flight: {
        flightNumber: "ELZ4321",
        origin: "DAL",
        destination: "MDW",
        travelDate: "2099-09-21",
        status: "ON_TIME",
        summary: "Mock upcoming trip is on time.",
      },
    },
  }, {
    vars: {
      ...context.vars,
      expected_execution_mode: "remote",
    },
  });

  assert.equal(result.pass, false);
  assert.match(result.reason, /executionMode must be local or deployed/);
});
