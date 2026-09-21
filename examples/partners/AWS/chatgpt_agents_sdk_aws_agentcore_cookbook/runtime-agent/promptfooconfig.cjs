const fs = require("node:fs");
const path = require("node:path");
const { demoTravelDate, materializeDemoDate } = require("./demo-date.cjs");

const fixturePath = path.join(
  __dirname,
  "evals",
  "fixtures",
  "flight-status-results.jsonl",
);

function loadCases() {
  const lines = fs.readFileSync(fixturePath, "utf8").split(/\r?\n/).filter(Boolean);
  if (lines.length === 0) {
    throw new Error(`${fixturePath} contains no evaluation cases`);
  }

  const travelDate = demoTravelDate();
  return lines.map((line, index) => {
    let record;
    try {
      record = materializeDemoDate(JSON.parse(line), travelDate);
    } catch (error) {
      throw new Error(`${fixturePath}:${index + 1} is not valid JSON`, { cause: error });
    }

    for (const field of [
      "case_id",
      "expected_provider",
      "expected_execution_mode",
      "expected_action",
      "output",
    ]) {
      if (record[field] === undefined) {
        throw new Error(`${fixturePath}:${index + 1} is missing ${field}`);
      }
    }
    if (!record.output || typeof record.output !== "object" || Array.isArray(record.output)) {
      throw new Error(`${fixturePath}:${index + 1} output must be a JSON object`);
    }
    if (!["local", "deployed"].includes(record.expected_execution_mode)) {
      throw new Error(
        `${fixturePath}:${index + 1} has an invalid expected_execution_mode`,
      );
    }
    if (
      record.expected_contract_valid !== undefined
      && typeof record.expected_contract_valid !== "boolean"
    ) {
      throw new Error(
        `${fixturePath}:${index + 1} expected_contract_valid must be a boolean`,
      );
    }
    return record;
  });
}

module.exports = {
  description: "Offline flight Runtime response contract",
  prompts: ["{{observed_output}}"],
  providers: [{ id: "echo", label: "checked-in Runtime response fixture" }],
  sharing: false,
  writeLatestResults: true,
  tests: loadCases().map((record) => ({
    description: record.case_id,
    vars: {
      observed_output: JSON.stringify(record.output),
      expected_provider: record.expected_provider,
      expected_execution_mode: record.expected_execution_mode,
      expected_action: record.expected_action,
      expected_contract_valid: record.expected_contract_valid !== false,
    },
    metadata: {
      case_id: record.case_id,
      expected_contract_valid: record.expected_contract_valid !== false,
    },
    assert: [
      {
        type: "javascript",
        metric: "runtime-contract",
        value: "file://evals/assert-runtime-contract.cjs",
      },
    ],
  })),
};
