const { spawn } = require("node:child_process");
const { randomUUID } = require("node:crypto");
const path = require("node:path");

const RESULT_PREFIX = "COOKBOOK_LOCAL_AGENT_RESULT=";
const DEFAULT_TIMEOUT_MS = 180_000;
const MAX_OUTPUT_BYTES = 1_048_576;
const TERMINATION_GRACE_MS = 5_000;
const CHILD_ENV_NAMES = new Set([
  "COOKBOOK_DEMO_TRAVEL_DATE",
  "COOKBOOK_TRACING_MODE",
  "CURL_CA_BUNDLE",
  "HOME",
  "HTTP_PROXY",
  "HTTPS_PROXY",
  "LANG",
  "LOCAL_AGENT_LOG_GROUP",
  "LOCAL_AGENT_SERVICE_NAME",
  "NO_PROXY",
  "NODE_EXTRA_CA_CERTS",
  "OPENAI_AGENTS_MODEL",
  "OPENAI_API_KEY",
  "OPENAI_BASE_URL",
  "OPENAI_PROJECT_ID",
  "OPENAI_TRACE_API_KEY",
  "OPENAI_TRACE_WORKFLOW_NAME",
  "PATH",
  "REQUESTS_CA_BUNDLE",
  "SSL_CERT_DIR",
  "SSL_CERT_FILE",
  "TEMP",
  "TMP",
  "TMPDIR",
  "UV_BIN",
  "UV_CACHE_DIR",
  "UV_NO_CACHE",
  "UV_OFFLINE",
  "UV_PROJECT_ENVIRONMENT",
  "UV_PYTHON",
  "UV_PYTHON_DOWNLOADS",
  "UV_SYSTEM_PYTHON",
  "VIRTUAL_ENV",
  "http_proxy",
  "https_proxy",
  "no_proxy",
]);
const SENSITIVE_ENV_NAME = /key|token|secret|password|credential/i;

function validatedBedrockEnvironment(env) {
  const awsRegion = env.AWS_REGION?.trim();
  const awsDefaultRegion = env.AWS_DEFAULT_REGION?.trim();
  if (awsRegion && awsDefaultRegion && awsRegion !== awsDefaultRegion) {
    throw new Error("AWS_REGION and AWS_DEFAULT_REGION must match");
  }
  const region = awsRegion || awsDefaultRegion;
  if (!region) {
    throw new Error("AWS_REGION or AWS_DEFAULT_REGION is required");
  }
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)+$/.test(region)) {
    throw new Error("The configured AWS region is invalid");
  }
  const endpoint = env.OPENAI_BASE_URL?.trim();
  const canonical = `https://bedrock-mantle.${region}.api.aws/v1`;
  if (!endpoint || endpoint !== env.OPENAI_BASE_URL || endpoint.includes("\\")) {
    throw new Error("OPENAI_BASE_URL is not an approved AWS Bedrock endpoint");
  }
  let parsed;
  try {
    parsed = new URL(endpoint);
  } catch {
    throw new Error("OPENAI_BASE_URL is not an approved AWS Bedrock endpoint");
  }
  if (
    parsed.protocol !== "https:"
    || parsed.username
    || parsed.password
    || parsed.port
    || parsed.search
    || parsed.hash
    || parsed.hostname !== `bedrock-mantle.${region}.api.aws`
    || parsed.pathname !== "/v1"
    || endpoint !== canonical
  ) {
    throw new Error("OPENAI_BASE_URL is not an approved AWS Bedrock endpoint");
  }
  return { endpoint, region };
}

function requiredEnvironment(env) {
  if (env.RUN_PROMPTFOO_AGENT_EVALUATION !== "1") {
    throw new Error(
      "RUN_PROMPTFOO_AGENT_EVALUATION=1 is required for actual-agent evaluation",
    );
  }
  const tracingMode = tracingModeFromEnvironment(env);
  const required = ["OPENAI_API_KEY", "OPENAI_BASE_URL"];
  if (tracingMode === "dual") {
    required.push("OPENAI_TRACE_API_KEY");
  }
  const missing = required.filter((name) => !env[name]?.trim());
  if (!env.AWS_REGION?.trim() && !env.AWS_DEFAULT_REGION?.trim()) {
    missing.push("AWS_REGION or AWS_DEFAULT_REGION");
  }
  if (missing.length) {
    throw new Error(`Actual-agent evaluation is missing: ${missing.join(", ")}`);
  }
  if (
    tracingMode === "dual"
    && env.OPENAI_API_KEY.trim() === env.OPENAI_TRACE_API_KEY.trim()
  ) {
    throw new Error(
      "OPENAI_API_KEY and OPENAI_TRACE_API_KEY must use separate credentials",
    );
  }
  validatedBedrockEnvironment(env);
}

function tracingModeFromEnvironment(env) {
  const tracingMode = env.COOKBOOK_TRACING_MODE?.trim() || "aws";
  if (tracingMode !== "aws" && tracingMode !== "dual") {
    throw new Error("COOKBOOK_TRACING_MODE must be aws or dual");
  }
  return tracingMode;
}

function timeoutFromEnvironment(env) {
  const raw = env.PROMPTFOO_AGENT_EVALUATION_TIMEOUT_MS || String(DEFAULT_TIMEOUT_MS);
  const timeoutMs = Number(raw);
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1_000 || timeoutMs > 600_000) {
    throw new Error(
      "PROMPTFOO_AGENT_EVALUATION_TIMEOUT_MS must be an integer from 1000 to 600000",
    );
  }
  return timeoutMs;
}

function safeOtelValue(value) {
  return String(value).replace(/[\n\r,=]/g, "_");
}

function allowedChildEnvironment(env) {
  return Object.fromEntries(
    Object.entries(env).filter(([name]) => (
      CHILD_ENV_NAMES.has(name)
      || name.startsWith("AWS_")
      || name.startsWith("LC_")
    )),
  );
}

function buildAgentProcessSpec({
  request,
  runtimeSessionId,
  invocationId,
  abortSignal,
  env = process.env,
}) {
  const tracingMode = tracingModeFromEnvironment(env);
  const region = env.AWS_REGION?.trim() || env.AWS_DEFAULT_REGION.trim();
  const serviceName = env.LOCAL_AGENT_SERVICE_NAME?.trim()
    || "chatgpt-agentcore-cookbook-local";
  const logGroupName = env.LOCAL_AGENT_LOG_GROUP?.trim()
    || `/aws/bedrock-agentcore/runtimes/${serviceName}`;
  const allowedEnvironment = allowedChildEnvironment(env);
  if (tracingMode === "aws") {
    delete allowedEnvironment.OPENAI_TRACE_API_KEY;
    delete allowedEnvironment.OPENAI_PROJECT_ID;
  }
  const childEnv = {
    ...allowedEnvironment,
    AGENT_OBSERVABILITY_ENABLED: "true",
    AWS_REGION: region,
    AWS_DEFAULT_REGION: region,
    COOKBOOK_EXECUTION_MODE: "local",
    COOKBOOK_FORCE_LOCAL_TOOLS: "0",
    COOKBOOK_MANUAL_OPENAI_AGENTS_INSTRUMENTATION: "true",
    COOKBOOK_TRACING_MODE: tracingMode,
    DISABLE_ADOT_OBSERVABILITY: "false",
    OPENAI_TRACE_INCLUDE_SENSITIVE_DATA: "0",
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "false",
    OTEL_PYTHON_CONFIGURATOR: "aws_configurator",
    OTEL_PYTHON_DISABLED_INSTRUMENTATIONS: "openai_agents",
    OTEL_PYTHON_DISTRO: "aws_distro",
    OTEL_EXPORTER_OTLP_PROTOCOL: "http/protobuf",
    OTEL_RESOURCE_ATTRIBUTES: [
      `service.name=${safeOtelValue(serviceName)}`,
      `aws.log.group.names=${safeOtelValue(logGroupName)}`,
      "aws.service.type=gen_ai_agent",
      "deployment.environment.name=local",
      "evaluation.framework=promptfoo",
    ].join(","),
    OTEL_EXPORTER_OTLP_LOGS_HEADERS: [
      `x-aws-log-group=${safeOtelValue(logGroupName)}`,
      "x-aws-log-stream=runtime-logs",
      "x-aws-metric-namespace=bedrock-agentcore",
    ].join(","),
    OTEL_SDK_DISABLED: "false",
    OTEL_TRACES_EXPORTER: "otlp",
  };
  return {
    command: env.UV_BIN?.trim() || "uv",
    args: ["run", "--locked", "opentelemetry-instrument", "python", "local_invoke.py"],
    cwd: path.resolve(__dirname, ".."),
    env: childEnv,
    abortSignal,
    timeoutMs: timeoutFromEnvironment(env),
    input: JSON.stringify({
      request,
      runtime_session_id: runtimeSessionId,
      invocation_id: invocationId,
      execution_mode: "local",
    }),
  };
}

function sanitizeDiagnostic(value, env = process.env) {
  let diagnostic = String(value);
  for (const [name, secret] of Object.entries(env)) {
    if (SENSITIVE_ENV_NAME.test(name) && secret && secret.length >= 4) {
      diagnostic = diagnostic.split(secret).join("[REDACTED]");
    }
  }
  diagnostic = diagnostic
    .replace(
      /\b((?:[a-z][a-z0-9+.-]*:)?\/\/)[^/\s@]+@/gi,
      "$1[REDACTED]@",
    )
    .replace(/\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/g, "[REDACTED_AWS_ACCESS_KEY]")
    .replace(/(Bearer\s+)[^\s]+/gi, "$1[REDACTED]")
    .replace(/((?:api[_-]?key|session[_-]?token)\s*[=:]\s*)[^\s,;]+/gi, "$1[REDACTED]");
  return diagnostic.slice(-4_000);
}

function runAgentProcess(
  input,
  {
    spawnImpl = spawn,
    timeoutMsOverride,
    terminationGraceMs = TERMINATION_GRACE_MS,
  } = {},
) {
  const spec = buildAgentProcessSpec(input);
  if (timeoutMsOverride !== undefined) {
    spec.timeoutMs = timeoutMsOverride;
  }
  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawnImpl(spec.command, spec.args, {
        cwd: spec.cwd,
        env: spec.env,
        shell: false,
        stdio: ["pipe", "pipe", "pipe"],
      });
    } catch (error) {
      reject(error);
      return;
    }

    let stdout = "";
    let stderr = "";
    let settled = false;
    let terminationError;
    let terminationDeadlineTimer;
    let forceKillTimer;
    let timer;
    const abortHandler = () => {
      requestTermination(new Error("Actual-agent evaluation was aborted"));
    };
    const finish = (error, output) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearTimeout(forceKillTimer);
      clearTimeout(terminationDeadlineTimer);
      spec.abortSignal?.removeEventListener("abort", abortHandler);
      if (error) reject(error);
      else resolve(output);
    };
    const requestTermination = (error) => {
      if (terminationError || settled) return;
      terminationError = error;
      child.kill("SIGTERM");
      forceKillTimer = setTimeout(() => {
        terminationDeadlineTimer = setTimeout(() => {
          finish(error);
        }, terminationGraceMs);
        child.kill("SIGKILL");
      }, terminationGraceMs);
    };
    timer = setTimeout(() => {
      requestTermination(
        new Error(`Actual-agent evaluation timed out after ${spec.timeoutMs}ms`),
      );
    }, spec.timeoutMs);
    if (spec.abortSignal?.aborted) {
      requestTermination(new Error("Actual-agent evaluation was aborted"));
    } else {
      spec.abortSignal?.addEventListener("abort", abortHandler, { once: true });
    }

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      const nextSize = Buffer.byteLength(stdout, "utf8")
        + Buffer.byteLength(chunk, "utf8");
      if (nextSize > MAX_OUTPUT_BYTES) {
        requestTermination(new Error("Actual-agent evaluation output exceeded 1 MiB"));
        return;
      }
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr = `${stderr}${chunk}`.slice(-8_000);
    });
    child.stdin.once("error", (error) => requestTermination(error));
    child.on("error", (error) => {
      if (terminationError) {
        return;
      }
      finish(error);
    });
    child.once("close", (code) => {
      if (terminationError) {
        finish(terminationError);
        return;
      }
      if (code !== 0) {
        const diagnostic = sanitizeDiagnostic(stderr, spec.env);
        finish(new Error(
          `Actual-agent process exited with code ${code ?? "unknown"}`
          + (diagnostic ? `: ${diagnostic}` : ""),
        ));
        return;
      }
      finish(undefined, stdout);
    });
    child.stdin.end(spec.input);
  });
}

function parseStructuredResult(stdout, runtimeSessionId, invocationId) {
  const resultLines = stdout.split(/\r?\n/)
    .filter((line) => line.startsWith(RESULT_PREFIX));
  if (resultLines.length !== 1) {
    throw new Error(
      resultLines.length
        ? "Actual-agent process returned multiple structured results"
        : "Actual-agent process returned no structured result",
    );
  }
  let parsed;
  try {
    parsed = JSON.parse(resultLines[0].slice(RESULT_PREFIX.length));
  } catch {
    throw new Error("Actual-agent process returned invalid structured JSON");
  }
  if (
    parsed.trace?.runtimeSessionId !== runtimeSessionId
    || parsed.trace?.invocationId !== invocationId
  ) {
    throw new Error("Actual-agent process returned mismatched correlation IDs");
  }
  const { trace, ...output } = parsed;
  return { output, trace };
}

class AgentsSdkProvider {
  constructor(options = {}, dependencies = {}) {
    this.providerId = options.id || "local-agents-sdk";
    this.runProcess = dependencies.runProcess || runAgentProcess;
    this.idFactory = dependencies.idFactory || randomUUID;
    this.env = dependencies.env || process.env;
    this.runtimeSessionId = `promptfoo-${this.idFactory()}`;
  }

  id() {
    return this.providerId;
  }

  async callApi(prompt, context = {}, options = {}) {
    try {
      requiredEnvironment(this.env);
      const caseId = String(context.vars?.case_id || "");
      if (!/^[a-z0-9][a-z0-9-]{0,63}$/.test(caseId)) {
        throw new Error("Actual-agent evaluation requires a valid case_id");
      }
      let request;
      try {
        request = JSON.parse(prompt);
      } catch {
        throw new Error("Actual-agent evaluation request is not valid JSON");
      }
      if (!request || typeof request !== "object" || Array.isArray(request)) {
        throw new Error("Actual-agent evaluation request must be a JSON object");
      }
      if (request.action !== context.vars?.expected_action) {
        throw new Error("Actual-agent evaluation request action does not match the case");
      }

      const invocationId = `promptfoo-${caseId}-${this.idFactory()}`;
      const stdout = await this.runProcess({
        request,
        runtimeSessionId: this.runtimeSessionId,
        invocationId,
        abortSignal: options.abortSignal,
        env: this.env,
      });
      const result = parseStructuredResult(
        stdout,
        this.runtimeSessionId,
        invocationId,
      );
      return {
        output: result.output,
        metadata: {
          evaluation_case_id: caseId,
          runtime_session_id: result.trace.runtimeSessionId,
          invocation_id: result.trace.invocationId,
        },
      };
    } catch (error) {
      return {
        error: sanitizeDiagnostic(
          error instanceof Error ? error.message : String(error),
          this.env,
        ),
      };
    }
  }
}

module.exports = AgentsSdkProvider;
module.exports.allowedChildEnvironment = allowedChildEnvironment;
module.exports.buildAgentProcessSpec = buildAgentProcessSpec;
module.exports.parseStructuredResult = parseStructuredResult;
module.exports.requiredEnvironment = requiredEnvironment;
module.exports.runAgentProcess = runAgentProcess;
module.exports.sanitizeDiagnostic = sanitizeDiagnostic;
module.exports.validatedBedrockEnvironment = validatedBedrockEnvironment;
module.exports.tracingModeFromEnvironment = tracingModeFromEnvironment;
