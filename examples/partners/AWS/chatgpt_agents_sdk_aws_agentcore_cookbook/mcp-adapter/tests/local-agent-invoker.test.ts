import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";

import { describe, expect, it, vi } from "vitest";

import {
  buildLocalAgentEnvironment,
  createLocalAgentInvoker,
  LocalAgentConfig,
  LocalAgentProcessInput,
  runLocalAgentProcess,
  SpawnLocalAgentProcess,
  tracingModeFromEnvironment
} from "../providers/local-agent-invoker.js";

const config: LocalAgentConfig = {
  runtimeAgentDirectory: "/tmp/runtime-agent",
  uvExecutable: "/tmp/bin/uv",
  serviceName: "cookbook-local-agent",
  logGroupName: "/aws/bedrock-agentcore/runtimes/cookbook-local-agent"
};

const validModelEnvironment = {
  AWS_REGION: "us-west-2",
  OPENAI_API_KEY: "bedrock-model-key",
  OPENAI_BASE_URL: "https://bedrock-mantle.us-west-2.api.aws/v1"
};

type FakeChild = Omit<
  ChildProcessWithoutNullStreams,
  "stdin" | "stdout" | "stderr"
> & {
  stdin: PassThrough;
  stdout: PassThrough;
  stderr: PassThrough;
  signals: (NodeJS.Signals | number | undefined)[];
};

function processInput(overrides: Partial<LocalAgentProcessInput> = {}): LocalAgentProcessInput {
  return {
    request: { action: "get_upcoming_status" },
    runtimeSessionId: "local-session-123",
    invocationId: "local-invocation-456",
    executionMode: "local",
    config,
    ...overrides
  };
}

function createFakeChild(
  {
    closeOnSignal = "SIGTERM",
    errorOnSignal
  }: {
    closeOnSignal?: NodeJS.Signals | null;
    errorOnSignal?: NodeJS.Signals;
  } = {}
): FakeChild {
  const child = Object.assign(new EventEmitter(), {
    stdout: new PassThrough(),
    stderr: new PassThrough(),
    stdin: new PassThrough(),
    signals: [] as (NodeJS.Signals | number | undefined)[]
  }) as unknown as FakeChild;
  child.kill = vi.fn((signal?: NodeJS.Signals | number) => {
    child.signals.push(signal);
    if (signal === errorOnSignal) {
      queueMicrotask(() => child.emit("error", new Error(`Could not send ${signal}`)));
    }
    if (signal === closeOnSignal) {
      queueMicrotask(() => child.emit("close", null, signal));
    }
    return true;
  });
  return child;
}

describe("local Python agent invoker", () => {
  it("passes one correlation ID to the local run and parses its structured result", async () => {
    let observed: LocalAgentProcessInput | undefined;
    const invoke = createLocalAgentInvoker(
      config,
      async (input) => {
        observed = input;
        return [
          "ADOT startup output",
          `COOKBOOK_LOCAL_AGENT_RESULT=${JSON.stringify({
            provider: "agentcore-runtime",
            action: "get_upcoming_status",
            data: {
              flight: {
                flightNumber: "ELZ4321",
                origin: "DAL",
                destination: "MDW",
                travelDate: "2099-09-21",
                status: "ON_TIME",
                summary: "Sample trip is on time."
              }
            },
            trace: { runtimeSessionId: "local-session-123" }
          })}`
        ].join("\n");
      },
      () => "local-session-123"
    );

    await expect(invoke({ action: "get_upcoming_status" })).resolves.toMatchObject({
      executionMode: "local",
      action: "get_upcoming_status",
      trace: { runtimeSessionId: "local-session-123" }
    });
    expect(observed).toEqual({
      request: { action: "get_upcoming_status" },
      runtimeSessionId: "local-session-123",
      invocationId: "local-session-123",
      executionMode: "local",
      config
    });
  });

  it("overrides a stale agent mode with the selected local route", async () => {
    const invoke = createLocalAgentInvoker(
      config,
      async () => `COOKBOOK_LOCAL_AGENT_RESULT=${JSON.stringify({
        provider: "agentcore-runtime",
        executionMode: "deployed",
        action: "get_upcoming_status",
        data: {
          flight: {
            flightNumber: "ELZ4321",
            origin: "DAL",
            destination: "MDW",
            travelDate: "2099-09-21",
            status: "ON_TIME",
            summary: "Sample trip is on time."
          }
        }
      })}`,
      () => "local-session-123"
    );

    await expect(invoke({ action: "get_upcoming_status" })).resolves.toMatchObject({
      executionMode: "local"
    });
  });

  it("groups separate invocations from one ChatGPT conversation in one session", async () => {
    const observed: LocalAgentProcessInput[] = [];
    const invocationIds = ["invocation-1", "invocation-2"];
    const invoke = createLocalAgentInvoker(
      config,
      async (input) => {
        observed.push(input);
        return `COOKBOOK_LOCAL_AGENT_RESULT=${JSON.stringify({
          provider: "agentcore-runtime",
          action: "get_upcoming_status",
          data: {
            flight: {
              flightNumber: "ELZ4321",
              origin: "DAL",
              destination: "MDW",
              travelDate: "2099-09-21",
              status: "ON_TIME",
              summary: "Sample trip is on time."
            }
          },
          trace: {
            runtimeSessionId: input.runtimeSessionId,
            invocationId: input.invocationId
          }
        })}`;
      },
      () => invocationIds.shift()!
    );

    const context = { chatgptSessionId: "anonymous-chatgpt-conversation" };
    await invoke({ action: "get_upcoming_status" }, context);
    await invoke({ action: "get_upcoming_status" }, context);

    expect(observed[0]!.runtimeSessionId).toBe(observed[1]!.runtimeSessionId);
    expect(observed[0]!.runtimeSessionId).toMatch(/^chatgpt-[a-f0-9]{64}$/);
    expect(observed.map(({ invocationId }) => invocationId)).toEqual([
      "invocation-1",
      "invocation-2"
    ]);
  });

  it("rejects output without the structured-result marker", async () => {
    const invoke = createLocalAgentInvoker(config, async () => "unrelated output");

    await expect(invoke({ action: "get_upcoming_status" })).rejects.toThrow(
      "no structured result"
    );
  });

  it("uses AWS-only tracing by default and keeps the platform trace key out of the child", () => {
    const environment = buildLocalAgentEnvironment(
      processInput({
        config: {
          ...config,
          serviceName: "cookbook,local\nagent",
          logGroupName: "/aws/example=group"
        }
      }),
      {
        AWS_PROFILE: "agentcore-dev",
        AWS_REGION: "us-east-1",
        COOKBOOK_DEMO_TRAVEL_DATE: "2099-09-21",
        LC_ALL: "en_US.UTF-8",
        OPENAI_API_KEY: "bedrock-model-key",
        OPENAI_BASE_URL: "https://bedrock-mantle.us-east-1.api.aws/v1",
        OPENAI_TRACE_API_KEY: "openai-trace-key",
        OPENAI_TRACE_INCLUDE_SENSITIVE_DATA: "1",
        OTEL_EXPORTER_OTLP_ENDPOINT: "https://stale.example",
        PATH: "/usr/bin",
        UNRELATED_SECRET: "must-not-reach-child",
        UV_CACHE_DIR: "/tmp/uv-cache"
      }
    );

    expect(environment).toMatchObject({
      AWS_DEFAULT_REGION: "us-east-1",
      AWS_PROFILE: "agentcore-dev",
      AWS_REGION: "us-east-1",
      COOKBOOK_DEMO_TRAVEL_DATE: "2099-09-21",
      COOKBOOK_EXECUTION_MODE: "local",
      COOKBOOK_FORCE_LOCAL_TOOLS: "0",
      COOKBOOK_MANUAL_OPENAI_AGENTS_INSTRUMENTATION: "true",
      COOKBOOK_TRACING_MODE: "aws",
      LC_ALL: "en_US.UTF-8",
      OPENAI_API_KEY: "bedrock-model-key",
      OPENAI_BASE_URL: "https://bedrock-mantle.us-east-1.api.aws/v1",
      OPENAI_TRACE_INCLUDE_SENSITIVE_DATA: "0",
      OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "false",
      OTEL_PYTHON_DISABLED_INSTRUMENTATIONS: "openai_agents",
      OTEL_SDK_DISABLED: "false",
      PATH: "/usr/bin",
      UV_CACHE_DIR: "/tmp/uv-cache"
    });
    expect(environment.UNRELATED_SECRET).toBeUndefined();
    expect(environment.OTEL_EXPORTER_OTLP_ENDPOINT).toBeUndefined();
    expect(environment.OPENAI_TRACE_API_KEY).toBeUndefined();
    expect(environment.OTEL_RESOURCE_ATTRIBUTES).not.toMatch(/[\n\r]/);
    expect(environment.OTEL_RESOURCE_ATTRIBUTES).toContain(
      "service.name=cookbook_local_agent"
    );
    expect(environment.OTEL_EXPORTER_OTLP_LOGS_HEADERS).toContain(
      "x-aws-log-group=/aws/example_group"
    );
  });

  it("forwards only the dual-mode trace credential and project routing", () => {
    const environment = buildLocalAgentEnvironment(processInput(), {
      AWS_REGION: "us-east-1",
      COOKBOOK_TRACING_MODE: "dual",
      OPENAI_API_KEY: "bedrock-model-key",
      OPENAI_BASE_URL: "https://bedrock-mantle.us-east-1.api.aws/v1",
      OPENAI_PROJECT_ID: "proj_platform",
      OPENAI_TRACE_API_KEY: "openai-trace-key"
    });

    expect(environment.COOKBOOK_TRACING_MODE).toBe("dual");
    expect(environment.OPENAI_API_KEY).toBe("bedrock-model-key");
    expect(environment.OPENAI_TRACE_API_KEY).toBe("openai-trace-key");
    expect(environment.OPENAI_PROJECT_ID).toBe("proj_platform");
  });

  it("rejects unknown tracing modes before spawning a child", () => {
    expect(() => tracingModeFromEnvironment({ COOKBOOK_TRACING_MODE: "openai" }))
      .toThrow("COOKBOOK_TRACING_MODE must be aws or dual");
  });

  it("spawns the instrumented agent with a bounded allowlisted environment", async () => {
    const child = createFakeChild();
    let observed:
      | { command: string; args: readonly string[]; env: NodeJS.ProcessEnv }
      | undefined;
    let stdin = "";
    child.stdin.setEncoding("utf8");
    child.stdin.on("data", (chunk: string) => { stdin += chunk; });
    const spawnImpl: SpawnLocalAgentProcess = (command, args, options) => {
      observed = { command, args, env: options.env ?? {} };
      return child;
    };

    const pending = runLocalAgentProcess(processInput(), {
      env: {
        AWS_REGION: "us-west-2",
        COOKBOOK_TRACING_MODE: "dual",
        OPENAI_API_KEY: "bedrock-model-key",
        OPENAI_BASE_URL: "https://bedrock-mantle.us-west-2.api.aws/v1",
        OPENAI_TRACE_API_KEY: "openai-trace-key",
        PATH: "/usr/bin",
        UNRELATED_SECRET: "must-not-reach-child"
      },
      spawnImpl
    });
    child.stdout.write("COOKBOOK_LOCAL_AGENT_RESULT={\"ok\":true}\n");
    child.emit("close", 0, null);

    await expect(pending).resolves.toBe(
      "COOKBOOK_LOCAL_AGENT_RESULT={\"ok\":true}\n"
    );
    expect(observed?.command).toBe(config.uvExecutable);
    expect(observed?.args).toEqual([
      "run",
      "--locked",
      "opentelemetry-instrument",
      "python",
      "local_invoke.py"
    ]);
    expect(observed?.env.UNRELATED_SECRET).toBeUndefined();
    expect(JSON.parse(stdin)).toEqual({
      request: { action: "get_upcoming_status" },
      runtime_session_id: "local-session-123",
      invocation_id: "local-invocation-456",
      execution_mode: "local"
    });
  });

  it("rejects an unapproved model endpoint before spawning a credentialed child", async () => {
    const spawnImpl = vi.fn<SpawnLocalAgentProcess>();

    await expect(runLocalAgentProcess(processInput(), {
      env: {
        ...validModelEnvironment,
        OPENAI_BASE_URL: "https://bedrock-mantle.us-west-2.api.aws.evil.example/v1"
      },
      spawnImpl
    })).rejects.toThrow("not an approved AWS Bedrock endpoint");

    expect(spawnImpl).not.toHaveBeenCalled();
  });

  it("waits for SIGTERM and escalates a timed-out process to SIGKILL", async () => {
    const child = createFakeChild({ closeOnSignal: "SIGKILL" });
    const pending = runLocalAgentProcess(processInput(), {
      env: validModelEnvironment,
      spawnImpl: () => child,
      timeoutMs: 5,
      terminationGraceMs: 5
    });

    await expect(pending).rejects.toThrow("timed out after 5ms");
    expect(child.signals).toEqual(["SIGTERM", "SIGKILL"]);
  });

  it("keeps SIGKILL escalation armed when SIGTERM emits an error", async () => {
    const child = createFakeChild({
      closeOnSignal: "SIGKILL",
      errorOnSignal: "SIGTERM"
    });
    const pending = runLocalAgentProcess(processInput(), {
      env: validModelEnvironment,
      spawnImpl: () => child,
      timeoutMs: 5,
      terminationGraceMs: 5
    });

    await expect(pending).rejects.toThrow("timed out after 5ms");
    expect(child.signals).toEqual(["SIGTERM", "SIGKILL"]);
  });

  it("rejects at the final deadline when SIGKILL errors without close", async () => {
    const child = createFakeChild({
      closeOnSignal: null,
      errorOnSignal: "SIGKILL"
    });
    const pending = runLocalAgentProcess(processInput(), {
      env: validModelEnvironment,
      spawnImpl: () => child,
      timeoutMs: 5,
      terminationGraceMs: 5
    });

    await expect(pending).rejects.toThrow("timed out after 5ms");
    expect(child.signals).toEqual(["SIGTERM", "SIGKILL"]);
  }, 250);

  it.each(["stdout", "stderr"] as const)(
    "terminates when %s exceeds the bounded buffer",
    async (streamName) => {
      const child = createFakeChild();
      const pending = runLocalAgentProcess(processInput(), {
        env: validModelEnvironment,
        spawnImpl: () => child
      });

      child[streamName].write("x".repeat(1_048_577));

      await expect(pending).rejects.toThrow(
        `Local agent ${streamName} exceeded 1048576 bytes`
      );
      expect(child.signals).toEqual(["SIGTERM"]);
    }
  );

  it("redacts child credentials and bearer tokens from failure diagnostics", async () => {
    const child = createFakeChild();
    const pending = runLocalAgentProcess(processInput(), {
      env: {
        ...validModelEnvironment,
        COOKBOOK_TRACING_MODE: "dual",
        OPENAI_TRACE_API_KEY: "openai-trace-key",
        PATH: "/usr/bin"
      },
      spawnImpl: () => child
    });
    child.stderr.write(
      "model=bedrock-model-key trace=openai-trace-key "
      + "proxy=https://user:password@proxy.example Bearer bearer-value "
      + "secret=unlisted-secret"
    );
    child.emit("close", 1, null);

    const error = await pending.catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(Error);
    const message = (error as Error).message;
    expect(message).toContain("Local agent exited with code 1");
    expect(message).toContain("REDACTED");
    expect(message).not.toMatch(
      /bedrock-model-key|openai-trace-key|user:password|bearer-value|unlisted-secret/
    );
  });
});
