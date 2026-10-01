import { spawn } from "node:child_process";
import type {
  ChildProcessWithoutNullStreams,
  SpawnOptionsWithoutStdio
} from "node:child_process";
import { randomUUID } from "node:crypto";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { RuntimeRequest } from "../schemas/flight.js";
import {
  RuntimeInvocationContext,
  RuntimeInvoker
} from "./agentcore-runtime-flight-provider.js";
import { validateBedrockEnvironment } from "./bedrock-endpoint.js";
import { correlationSessionId } from "./runtime-correlation.js";

const LOCAL_RESULT_PREFIX = "COOKBOOK_LOCAL_AGENT_RESULT=";
const DEFAULT_SERVICE_NAME = "chatgpt-agentcore-cookbook-local";
const DEFAULT_TIMEOUT_MS = 180_000;
const MAX_OUTPUT_BYTES = 1_048_576;
const TERMINATION_GRACE_MS = 5_000;
const CHILD_ENV_NAMES = new Set([
  "COMSPEC",
  "COOKBOOK_DEMO_TRAVEL_DATE",
  "COOKBOOK_TRACING_MODE",
  "CURL_CA_BUNDLE",
  "HOME",
  "HTTPS_PROXY",
  "HTTP_PROXY",
  "LANG",
  "NO_PROXY",
  "NODE_EXTRA_CA_CERTS",
  "OPENAI_AGENTS_MODEL",
  "OPENAI_API_KEY",
  "OPENAI_BASE_URL",
  "OPENAI_PROJECT_ID",
  "OPENAI_TRACE_API_KEY",
  "OPENAI_TRACE_WORKFLOW_NAME",
  "PATH",
  "PATHEXT",
  "REQUESTS_CA_BUNDLE",
  "SSL_CERT_DIR",
  "SSL_CERT_FILE",
  "SYSTEMROOT",
  "TEMP",
  "TMP",
  "TMPDIR",
  "USERPROFILE",
  "UV_CACHE_DIR",
  "UV_NO_CACHE",
  "UV_OFFLINE",
  "UV_PROJECT_ENVIRONMENT",
  "UV_PYTHON",
  "UV_PYTHON_DOWNLOADS",
  "UV_SYSTEM_PYTHON",
  "VIRTUAL_ENV",
  "WINDIR",
  "http_proxy",
  "https_proxy",
  "no_proxy"
]);
const SENSITIVE_ENV_NAME = /key|token|secret|password|credential/i;

export interface LocalAgentConfig {
  runtimeAgentDirectory: string;
  uvExecutable: string;
  serviceName: string;
  logGroupName: string;
}

export interface LocalAgentProcessInput {
  request: RuntimeRequest;
  runtimeSessionId: string;
  invocationId: string;
  executionMode: "local";
  config: LocalAgentConfig;
}

export type RunLocalAgentProcess = (input: LocalAgentProcessInput) => Promise<string>;
export type SpawnLocalAgentProcess = (
  command: string,
  args: readonly string[],
  options: SpawnOptionsWithoutStdio
) => ChildProcessWithoutNullStreams;

export interface RunLocalAgentProcessOptions {
  spawnImpl?: SpawnLocalAgentProcess;
  timeoutMs?: number;
  terminationGraceMs?: number;
  env?: NodeJS.ProcessEnv;
}

function safeOtelValue(value: string): string {
  return value.replace(/[\n\r,=]/g, "_");
}

export function allowedLocalAgentEnvironment(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  return Object.fromEntries(
    Object.entries(env).filter(([name, value]) => (
      value !== undefined
      && (
        CHILD_ENV_NAMES.has(name)
        || name.startsWith("AWS_")
        || name.startsWith("LC_")
      )
    ))
  );
}

export function tracingModeFromEnvironment(
  env: NodeJS.ProcessEnv = process.env
): "aws" | "dual" {
  const tracingMode = env.COOKBOOK_TRACING_MODE?.trim() || "aws";
  if (tracingMode !== "aws" && tracingMode !== "dual") {
    throw new Error("COOKBOOK_TRACING_MODE must be aws or dual");
  }
  return tracingMode;
}

export function buildLocalAgentEnvironment(
  input: LocalAgentProcessInput,
  env: NodeJS.ProcessEnv = process.env
): NodeJS.ProcessEnv {
  const { region } = validateBedrockEnvironment(env);
  const serviceName = safeOtelValue(input.config.serviceName);
  const logGroupName = safeOtelValue(input.config.logGroupName);
  const tracingMode = tracingModeFromEnvironment(env);
  const childEnvironment = allowedLocalAgentEnvironment(env);
  if (tracingMode === "aws") {
    delete childEnvironment.OPENAI_TRACE_API_KEY;
    delete childEnvironment.OPENAI_PROJECT_ID;
  }
  return {
    ...childEnvironment,
    AGENT_OBSERVABILITY_ENABLED: "true",
    AWS_DEFAULT_REGION: region,
    AWS_REGION: region,
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
      `service.name=${serviceName}`,
      `aws.log.group.names=${logGroupName}`,
      "aws.service.type=gen_ai_agent",
      "deployment.environment.name=local"
    ].join(","),
    OTEL_EXPORTER_OTLP_LOGS_HEADERS: [
      `x-aws-log-group=${logGroupName}`,
      "x-aws-log-stream=runtime-logs",
      "x-aws-metric-namespace=bedrock-agentcore"
    ].join(","),
    OTEL_SDK_DISABLED: "false",
    OTEL_TRACES_EXPORTER: "otlp"
  };
}

export function sanitizeLocalAgentDiagnostic(
  value: unknown,
  env: NodeJS.ProcessEnv = process.env
): string {
  let diagnostic = String(value);
  for (const [name, secret] of Object.entries(env)) {
    if (SENSITIVE_ENV_NAME.test(name) && secret && secret.length >= 4) {
      diagnostic = diagnostic.split(secret).join("[REDACTED]");
    }
  }
  diagnostic = diagnostic
    .replace(
      /\b((?:[a-z][a-z0-9+.-]*:)?\/\/)[^/\s@]+@/gi,
      "$1[REDACTED]@"
    )
    .replace(/\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/g, "[REDACTED_AWS_ACCESS_KEY]")
    .replace(/(Bearer\s+)[^\s]+/gi, "$1[REDACTED]")
    .replace(
      /((?:api[_-]?key|access[_-]?key|session[_-]?token|secret|password|credential)\s*[=:]\s*)[^\s,;]+/gi,
      "$1[REDACTED]"
    );
  return diagnostic.slice(-4_000);
}

export function localAgentConfigFromEnv(): LocalAgentConfig {
  const serviceName = process.env.LOCAL_AGENT_SERVICE_NAME?.trim() || DEFAULT_SERVICE_NAME;
  const moduleDirectory = fileURLToPath(new URL(".", import.meta.url));
  const runtimeAgentCandidates = [
    resolve(moduleDirectory, "../../../runtime-agent"),
    resolve(moduleDirectory, "../../runtime-agent")
  ];
  const uvCandidates = [
    process.env.UV_BIN?.trim(),
    join(homedir(), ".local", "bin", process.platform === "win32" ? "uv.exe" : "uv"),
    "/opt/homebrew/bin/uv",
    "/usr/local/bin/uv"
  ].filter((candidate): candidate is string => Boolean(candidate));
  return {
    runtimeAgentDirectory: process.env.RUNTIME_AGENT_DIRECTORY?.trim()
      || runtimeAgentCandidates.find((candidate) => existsSync(join(candidate, "pyproject.toml")))
      || runtimeAgentCandidates[0],
    uvExecutable: uvCandidates.find(existsSync) || "uv",
    serviceName,
    logGroupName: process.env.LOCAL_AGENT_LOG_GROUP?.trim()
      || `/aws/bedrock-agentcore/runtimes/${serviceName}`
  };
}

export async function runLocalAgentProcess(
  input: LocalAgentProcessInput,
  {
    spawnImpl = spawn as SpawnLocalAgentProcess,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    terminationGraceMs = TERMINATION_GRACE_MS,
    env = process.env
  }: RunLocalAgentProcessOptions = {}
): Promise<string> {
  return new Promise<string>((resolvePromise, reject) => {
    const childEnv = buildLocalAgentEnvironment(input, env);
    let child: ChildProcessWithoutNullStreams;
    try {
      child = spawnImpl(
        input.config.uvExecutable,
        ["run", "--locked", "opentelemetry-instrument", "python", "local_invoke.py"],
        {
          cwd: input.config.runtimeAgentDirectory,
          env: childEnv,
          stdio: ["pipe", "pipe", "pipe"]
        }
      );
    } catch (error) {
      reject(error);
      return;
    }

    let stdout = "";
    let stderr = "";
    let stdoutBytes = 0;
    let stderrBytes = 0;
    let settled = false;
    let terminationError: Error | undefined;
    let terminationDeadlineTimer: NodeJS.Timeout | undefined;
    let forceKillTimer: NodeJS.Timeout | undefined;
    let timeoutTimer: NodeJS.Timeout | undefined;

    const finish = (error?: Error, output?: string) => {
      if (settled) return;
      settled = true;
      if (timeoutTimer) clearTimeout(timeoutTimer);
      if (forceKillTimer) clearTimeout(forceKillTimer);
      if (terminationDeadlineTimer) clearTimeout(terminationDeadlineTimer);
      if (error) reject(error);
      else resolvePromise(output ?? "");
    };
    const requestTermination = (error: Error) => {
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
    const appendOutput = (
      current: string,
      currentBytes: number,
      chunk: string,
      label: "stdout" | "stderr"
    ): [string, number] => {
      const chunkBytes = Buffer.byteLength(chunk, "utf8");
      if (currentBytes + chunkBytes > MAX_OUTPUT_BYTES) {
        requestTermination(
          new Error(`Local agent ${label} exceeded ${MAX_OUTPUT_BYTES} bytes`)
        );
        return [current, currentBytes];
      }
      return [`${current}${chunk}`, currentBytes + chunkBytes];
    };

    timeoutTimer = setTimeout(() => {
      requestTermination(new Error(`Local agent timed out after ${timeoutMs}ms`));
    }, timeoutMs);

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      [stdout, stdoutBytes] = appendOutput(stdout, stdoutBytes, chunk, "stdout");
    });
    child.stderr.on("data", (chunk: string) => {
      [stderr, stderrBytes] = appendOutput(stderr, stderrBytes, chunk, "stderr");
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
        const diagnostic = sanitizeLocalAgentDiagnostic(stderr, childEnv);
        finish(new Error(
          `Local agent exited with code ${code ?? "unknown"}`
          + (diagnostic ? `: ${diagnostic}` : "")
        ));
        return;
      }
      finish(undefined, stdout);
    });
    child.stdin.end(JSON.stringify({
      request: input.request,
      runtime_session_id: input.runtimeSessionId,
      invocation_id: input.invocationId,
      execution_mode: input.executionMode
    }));
  });
}

export function createLocalAgentInvoker(
  config: LocalAgentConfig = localAgentConfigFromEnv(),
  runProcess: RunLocalAgentProcess = runLocalAgentProcess,
  sessionIdFactory: () => string = randomUUID
): RuntimeInvoker {
  return async (request: RuntimeRequest, context?: RuntimeInvocationContext) => {
    const invocationId = sessionIdFactory();
    const runtimeSessionId = correlationSessionId(context, invocationId);
    const stdout = await runProcess({
      request,
      runtimeSessionId,
      invocationId,
      executionMode: "local",
      config
    });
    const resultLine = stdout.split(/\r?\n/)
      .find((line) => line.startsWith(LOCAL_RESULT_PREFIX));
    if (!resultLine) throw new Error("Local agent returned no structured result");

    let parsed: unknown;
    try {
      parsed = JSON.parse(resultLine.slice(LOCAL_RESULT_PREFIX.length));
    } catch {
      throw new Error("Local agent returned invalid JSON");
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("Local agent returned a non-object JSON response");
    }
    return {
      ...parsed,
      executionMode: "local"
    };
  };
}
