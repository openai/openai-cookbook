import { describe, expect, it } from "vitest";
import {
  parseRealtimeEvent,
  readTaskNoteRequest,
} from "../src/mobile/realtime-events.js";

describe("Realtime event parsing", () => {
  it("rejects malformed and untyped messages", () => {
    expect(parseRealtimeEvent("not json")).toBeNull();
    expect(parseRealtimeEvent(JSON.stringify({ value: 1 }))).toBeNull();
    expect(parseRealtimeEvent(new Uint8Array())).toBeNull();
  });

  it("reads and bounds the expected tool request", () => {
    const event = parseRealtimeEvent(
      JSON.stringify({
        type: "response.function_call_arguments.done",
        call_id: "call_123",
        name: "save_task_note",
        arguments: JSON.stringify({
          title: `  ${"A".repeat(140)}  `,
          details: " Pick up the repaired lamp. ",
        }),
      }),
    );

    expect(event).not.toBeNull();
    const request = readTaskNoteRequest(event!);
    expect(request).toEqual({
      callId: "call_123",
      title: "A".repeat(120),
      details: "Pick up the repaired lamp.",
    });
  });

  it("ignores unrecognized tools and invalid arguments", () => {
    const wrongTool = parseRealtimeEvent(
      JSON.stringify({
        type: "response.function_call_arguments.done",
        call_id: "call_123",
        name: "delete_everything",
        arguments: "{}",
      }),
    );
    expect(readTaskNoteRequest(wrongTool!)).toBeNull();
  });
});
