const { isDeepStrictEqual } = require("node:util");

function parseObject(value, label) {
  let parsed = value;
  if (typeof value === "string") {
    try {
      parsed = JSON.parse(value);
    } catch {
      return { error: `${label} is not valid JSON` };
    }
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { error: `${label} must be a JSON object` };
  }
  return { value: parsed };
}

module.exports = (rawOutput, context) => {
  const actual = parseObject(rawOutput, "Actual agent output");
  if (actual.error) {
    return { pass: false, score: 0, reason: actual.error };
  }
  const expected = parseObject(context.vars.expected_output, "Expected agent output");
  if (expected.error) {
    return { pass: false, score: 0, reason: expected.error };
  }

  const pass = isDeepStrictEqual(actual.value, expected.value);
  return {
    pass,
    score: pass ? 1 : 0,
    reason: pass
      ? "Actual agent output exactly matches the canonical expected behavior"
      : "Actual agent output differs from the canonical expected behavior",
  };
};
