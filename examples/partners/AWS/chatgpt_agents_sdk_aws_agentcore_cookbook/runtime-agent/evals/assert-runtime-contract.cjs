function check(pass, reason) {
  return { pass, score: pass ? 1 : 0, reason };
}

const AIRPORT_CODE = /^[A-Z]{3}$/;
const TRAVEL_DATE = /^\d{4}-\d{2}-\d{2}$/;
const LOCAL_TIME = /^\d{2}:\d{2}$/;
const EXECUTION_MODES = new Set(["local", "deployed"]);

function isObject(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function hasExactKeys(value, requiredKeys, optionalKeys = []) {
  if (!isObject(value)) {
    return false;
  }
  const allowedKeys = new Set([...requiredKeys, ...optionalKeys]);
  const actualKeys = Object.keys(value);
  return (
    requiredKeys.every((key) => Object.hasOwn(value, key))
    && actualKeys.every((key) => allowedKeys.has(key))
  );
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.length > 0;
}

function matchesTrace(trace) {
  if (trace === undefined) {
    return true;
  }
  const keys = ["traceId", "requestId", "runtimeSessionId", "invocationId"];
  return (
    hasExactKeys(trace, [], keys)
    && Object.values(trace).every(isNonEmptyString)
  );
}

function matchesFlight(flight) {
  return (
    hasExactKeys(flight, [
      "flightNumber",
      "origin",
      "destination",
      "travelDate",
      "departTime",
      "arriveTime",
      "fareUsd",
    ])
    && isNonEmptyString(flight.flightNumber)
    && AIRPORT_CODE.test(flight.origin)
    && AIRPORT_CODE.test(flight.destination)
    && TRAVEL_DATE.test(flight.travelDate)
    && LOCAL_TIME.test(flight.departTime)
    && LOCAL_TIME.test(flight.arriveTime)
    && Number.isInteger(flight.fareUsd)
    && flight.fareUsd >= 0
  );
}

function matchesTripStatus(flight) {
  return (
    hasExactKeys(flight, [
      "flightNumber",
      "origin",
      "destination",
      "travelDate",
      "status",
      "summary",
    ])
    && isNonEmptyString(flight.flightNumber)
    && AIRPORT_CODE.test(flight.origin)
    && AIRPORT_CODE.test(flight.destination)
    && TRAVEL_DATE.test(flight.travelDate)
    && isNonEmptyString(flight.status)
    && isNonEmptyString(flight.summary)
  );
}

function matchesRuntimeResponse(output, expectedAction, expectedExecutionMode) {
  if (
    !hasExactKeys(
      output,
      ["provider", "executionMode", "action", "data"],
      ["trace"],
    )
    || output.provider !== "agentcore-runtime"
    || !EXECUTION_MODES.has(output.executionMode)
    || output.executionMode !== expectedExecutionMode
    || output.action !== expectedAction
    || !matchesTrace(output.trace)
  ) {
    return false;
  }

  if (expectedAction === "search_flights") {
    return (
      hasExactKeys(output.data, ["flights", "summary"])
      && Array.isArray(output.data.flights)
      && output.data.flights.every(matchesFlight)
      && isNonEmptyString(output.data.summary)
    );
  }
  if (["get_upcoming_status", "get_live_status"].includes(expectedAction)) {
    return (
      hasExactKeys(output.data, ["flight"])
      && matchesTripStatus(output.data.flight)
    );
  }
  return false;
}

module.exports = (rawOutput, context) => {
  const expectedValid = context.vars.expected_contract_valid !== false;
  let output = rawOutput;
  if (typeof output === "string") {
    try {
      output = JSON.parse(output);
    } catch {
      return {
        pass: !expectedValid,
        score: expectedValid ? 0 : 1,
        reason: expectedValid
          ? "Runtime contract mismatch: output is not valid JSON"
          : "Rejected as expected: output is not valid JSON",
      };
    }
  }

  if (!output || typeof output !== "object" || Array.isArray(output)) {
    return {
      pass: !expectedValid,
      score: expectedValid ? 0 : 1,
      reason: expectedValid
        ? "Runtime contract mismatch: output must be a JSON object"
        : "Rejected as expected: output must be a JSON object",
    };
  }

  const expectedProvider = context.vars.expected_provider;
  const expectedExecutionMode = context.vars.expected_execution_mode;
  const expectedAction = context.vars.expected_action;
  const components = [
    check(
      output.provider === expectedProvider,
      `provider ${output.provider === expectedProvider ? "matches" : "does not match"} ${expectedProvider}`,
    ),
    check(
      output.executionMode === expectedExecutionMode,
      `executionMode ${
        output.executionMode === expectedExecutionMode ? "matches" : "does not match"
      } ${expectedExecutionMode}`,
    ),
    check(
      EXECUTION_MODES.has(output.executionMode),
      "executionMode must be local or deployed",
    ),
    check(
      output.action === expectedAction,
      `action ${output.action === expectedAction ? "matches" : "does not match"} ${expectedAction}`,
    ),
    check(
      isObject(output.data),
      "output.data must be a JSON object",
    ),
    check(
      matchesRuntimeResponse(output, expectedAction, expectedExecutionMode),
      `${expectedAction} must match the strict Runtime response schema`,
    ),
  ];

  const failedReasons = components
    .filter((component) => !component.pass)
    .map((component) => component.reason);
  const contractValid = failedReasons.length === 0;
  const pass = contractValid === expectedValid;

  return {
    pass,
    score: pass ? 1 : 0,
    reason: expectedValid
      ? contractValid
        ? "Runtime contract matches"
        : `Runtime contract mismatch: ${failedReasons.join("; ")}`
      : contractValid
        ? "Expected the runtime contract to be rejected, but it matched"
        : `Rejected as expected: ${failedReasons.join("; ")}`,
    ...(expectedValid ? { componentResults: components } : {}),
  };
};
