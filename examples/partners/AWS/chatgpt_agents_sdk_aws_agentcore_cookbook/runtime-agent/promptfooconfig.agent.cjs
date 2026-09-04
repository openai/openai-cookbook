const {
  loadAgentEvaluationCases,
} = require("./evals/agent-evaluation-cases.cjs");

const cases = loadAgentEvaluationCases();

module.exports = {
  description: "Primary pre-promotion evaluation over actual OpenAI Agents SDK outputs",
  prompts: ["{{agent_request}}"],
  providers: [{
    "file://evals/agents-sdk-provider.cjs": {
      id: "local-agents-sdk",
      label: "instrumented local OpenAI Agents SDK",
      config: {},
    },
  }],
  sharing: false,
  writeLatestResults: false,
  tests: cases.map((record) => ({
    description: record.case_id,
    vars: {
      case_id: record.case_id,
      agent_request: JSON.stringify(record.aws_evaluation.request),
      expected_output: JSON.stringify(record.output),
      expected_provider: record.expected_provider,
      expected_execution_mode: record.expected_execution_mode,
      expected_action: record.expected_action,
      expected_contract_valid: true,
    },
    metadata: {
      case_id: record.case_id,
      evaluation_path: "actual-agents-sdk",
    },
    assert: [
      {
        type: "javascript",
        metric: "runtime-contract",
        value: "file://evals/assert-runtime-contract.cjs",
      },
      {
        type: "javascript",
        metric: "expected-behavior",
        value: "file://evals/assert-expected-output.cjs",
      },
    ],
  })),
};
