const fs = require("node:fs");
const path = require("node:path");
const { demoTravelDate, materializeDemoDate } = require("../demo-date.cjs");

const DEFAULT_FIXTURE_PATH = path.join(
  __dirname,
  "fixtures",
  "flight-status-results.jsonl",
);

function isObject(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function parseCaseIds(rawCaseIds) {
  if (!rawCaseIds || !rawCaseIds.trim()) {
    return [];
  }
  return [...new Set(rawCaseIds.split(",").map((value) => value.trim()).filter(Boolean))];
}

function loadAgentEvaluationCases({
  fixturePath = DEFAULT_FIXTURE_PATH,
  caseIds = parseCaseIds(process.env.PROMPTFOO_AGENT_EVALUATION_CASE_IDS),
  travelDate = demoTravelDate(),
} = {}) {
  const lines = fs.readFileSync(fixturePath, "utf8").split(/\r?\n/).filter(Boolean);
  if (lines.length === 0) {
    throw new Error(`${fixturePath} contains no evaluation cases`);
  }

  const records = lines.map((line, index) => {
    try {
      return materializeDemoDate(JSON.parse(line), travelDate);
    } catch (error) {
      throw new Error(`${fixturePath}:${index + 1} is not valid JSON`, { cause: error });
    }
  });

  const seenCaseIds = new Set();
  for (const [index, record] of records.entries()) {
    if (
      typeof record.case_id !== "string"
      || record.case_id.trim() !== record.case_id
      || !/^[a-z0-9][a-z0-9-]{0,63}$/.test(record.case_id)
    ) {
      throw new Error(`${fixturePath}:${index + 1} has an invalid case_id`);
    }
    if (seenCaseIds.has(record.case_id)) {
      throw new Error(`${fixturePath}:${index + 1} duplicates case_id ${record.case_id}`);
    }
    seenCaseIds.add(record.case_id);
    if (
      record.expected_contract_valid !== undefined
      && typeof record.expected_contract_valid !== "boolean"
    ) {
      throw new Error(
        `${fixturePath}:${index + 1} expected_contract_valid must be a boolean`,
      );
    }
    if (!["local", "deployed"].includes(record.expected_execution_mode)) {
      throw new Error(
        `${fixturePath}:${index + 1} has an invalid expected_execution_mode`,
      );
    }
  }

  const runnable = records.filter((record) => record.aws_evaluation);
  for (const record of runnable) {
    if (record.expected_contract_valid === false) {
      throw new Error(`${record.case_id} cannot be both runnable and expected-invalid`);
    }
    if (record.expected_execution_mode !== "local") {
      throw new Error(`${record.case_id} actual-agent evaluation must use local mode`);
    }
    if (!isObject(record.aws_evaluation.request)) {
      throw new Error(`${record.case_id} is missing a runnable request`);
    }
    if (!isObject(record.output)) {
      throw new Error(`${record.case_id} is missing its canonical output`);
    }
    if (!isObject(record.output.data)) {
      throw new Error(`${record.case_id} canonical output.data must be a JSON object`);
    }
    const action = record.aws_evaluation.request.action;
    if (action !== record.expected_action || action !== record.output.action) {
      throw new Error(`${record.case_id} request and expected actions do not match`);
    }
    if (record.output.provider !== record.expected_provider) {
      throw new Error(`${record.case_id} expected providers do not match`);
    }
    if (record.output.executionMode !== record.expected_execution_mode) {
      throw new Error(`${record.case_id} expected execution modes do not match`);
    }
  }

  const requestedIds = new Set(caseIds);
  const selected = requestedIds.size
    ? runnable.filter((record) => requestedIds.has(record.case_id))
    : runnable;
  const selectedIds = new Set(selected.map((record) => record.case_id));
  const unknownIds = [...requestedIds].filter((caseId) => !selectedIds.has(caseId));
  if (unknownIds.length) {
    throw new Error(`Unknown runnable evaluation case IDs: ${unknownIds.join(", ")}`);
  }
  if (selected.length === 0) {
    throw new Error("No runnable agent evaluation cases were selected");
  }
  return selected;
}

module.exports = {
  DEFAULT_FIXTURE_PATH,
  loadAgentEvaluationCases,
  parseCaseIds,
};
