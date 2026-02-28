import { expect, test } from "vitest";
import * as z from "zod/v4";

test("record should parse objects with non-function constructor field", () => {
  const schema = z.record(z.string(), z.any());

  expect(() => schema.parse({ constructor: "string", key: "value" })).not.toThrow();

  const result1 = schema.parse({ constructor: "string", key: "value" });
  expect(result1).toEqual({ constructor: "string", key: "value" });

  expect(() => schema.parse({ constructor: 123, key: "value" })).not.toThrow();

  const result2 = schema.parse({ constructor: 123, key: "value" });
  expect(result2).toEqual({ constructor: 123, key: "value" });

  expect(() => schema.parse({ constructor: null, key: "value" })).not.toThrow();

  const result3 = schema.parse({ constructor: null, key: "value" });
  expect(result3).toEqual({ constructor: null, key: "value" });

  expect(() => schema.parse({ constructor: {}, key: "value" })).not.toThrow();

  const result4 = schema.parse({ constructor: {}, key: "value" });
  expect(result4).toEqual({ constructor: {}, key: "value" });

  expect(() => schema.parse({ constructor: [], key: "value" })).not.toThrow();

  const result5 = schema.parse({ constructor: [], key: "value" });
  expect(result5).toEqual({ constructor: [], key: "value" });

  expect(() => schema.parse({ constructor: true, key: "value" })).not.toThrow();

  const result6 = schema.parse({ constructor: true, key: "value" });
  expect(result6).toEqual({ constructor: true, key: "value" });
});

test("record should still work with normal objects", () => {
  const schema = z.record(z.string(), z.string());

  expect(() => schema.parse({ normalKey: "value" })).not.toThrow();

  const result1 = schema.parse({ normalKey: "value" });
  expect(result1).toEqual({ normalKey: "value" });

  expect(() => schema.parse({ key1: "value1", key2: "value2" })).not.toThrow();

  const result2 = schema.parse({ key1: "value1", key2: "value2" });
  expect(result2).toEqual({ key1: "value1", key2: "value2" });
});

test("record should validate values according to schema even with constructor field", () => {
  const stringSchema = z.record(z.string(), z.string());

  expect(() => stringSchema.parse({ constructor: "string", key: "value" })).not.toThrow();

  expect(() => stringSchema.parse({ constructor: 123, key: "value" })).toThrow();
});

test("record should work with different key types and constructor field", () => {
  const enumSchema = z.record(z.enum(["constructor", "key"]), z.string());

  expect(() => enumSchema.parse({ constructor: "value1", key: "value2" })).not.toThrow();

  const result = enumSchema.parse({ constructor: "value1", key: "value2" });
  expect(result).toEqual({ constructor: "value1", key: "value2" });
});
