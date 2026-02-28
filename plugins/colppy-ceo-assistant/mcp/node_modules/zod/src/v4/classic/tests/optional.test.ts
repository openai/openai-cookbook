// @ts-ignore TS6133
import { expect, expectTypeOf, test } from "vitest";

import * as z from "zod/v4";

test(".optional()", () => {
  const schema = z.string().optional();
  expect(schema.parse("adsf")).toEqual("adsf");
  expect(schema.parse(undefined)).toEqual(undefined);
  expect(schema.safeParse(null).success).toEqual(false);

  expectTypeOf<typeof schema._output>().toEqualTypeOf<string | undefined>();
});

test("unwrap", () => {
  const unwrapped = z.string().optional().unwrap();
  expect(unwrapped).toBeInstanceOf(z.ZodString);
});

test("optionality", () => {
  const a = z.string();
  expect(a._zod.optin).toEqual(undefined);
  expect(a._zod.optout).toEqual(undefined);

  const b = z.string().optional();
  expect(b._zod.optin).toEqual("optional");
  expect(b._zod.optout).toEqual("optional");

  const c = z.string().default("asdf");
  expect(c._zod.optin).toEqual("optional");
  expect(c._zod.optout).toEqual(undefined);

  const d = z.string().optional().nullable();
  expect(d._zod.optin).toEqual("optional");
  expect(d._zod.optout).toEqual("optional");

  const e = z.string().default("asdf").nullable();
  expect(e._zod.optin).toEqual("optional");
  expect(e._zod.optout).toEqual(undefined);

  // z.undefined should NOT be optional
  const f = z.undefined();
  expect(f._zod.optin).toEqual("optional");
  expect(f._zod.optout).toEqual("optional");
  expectTypeOf<typeof f._zod.optin>().toEqualTypeOf<"optional" | undefined>();
  expectTypeOf<typeof f._zod.optout>().toEqualTypeOf<"optional" | undefined>();

  // z.union should be optional if any of the types are optional
  const g = z.union([z.string(), z.undefined()]);
  expect(g._zod.optin).toEqual("optional");
  expect(g._zod.optout).toEqual("optional");
  expectTypeOf<typeof g._zod.optin>().toEqualTypeOf<"optional" | undefined>();
  expectTypeOf<typeof g._zod.optout>().toEqualTypeOf<"optional" | undefined>();

  const h = z.union([z.string(), z.optional(z.string())]);
  expect(h._zod.optin).toEqual("optional");
  expect(h._zod.optout).toEqual("optional");
  expectTypeOf<typeof h._zod.optin>().toEqualTypeOf<"optional">();
  expectTypeOf<typeof h._zod.optout>().toEqualTypeOf<"optional">();
});

test("pipe optionality", () => {
  z.string().optional()._zod.optin;
  const a = z.string().optional().pipe(z.string());
  expect(a._zod.optin).toEqual("optional");
  expect(a._zod.optout).toEqual(undefined);
  expectTypeOf<typeof a._zod.optin>().toEqualTypeOf<"optional">();
  expectTypeOf<typeof a._zod.optout>().toEqualTypeOf<"optional" | undefined>();

  const b = z
    .string()
    .transform((val) => (Math.random() ? val : undefined))
    .pipe(z.string().optional());
  expect(b._zod.optin).toEqual(undefined);
  expect(b._zod.optout).toEqual("optional");
  expectTypeOf<typeof b._zod.optin>().toEqualTypeOf<"optional" | undefined>();
  expectTypeOf<typeof b._zod.optout>().toEqualTypeOf<"optional">();

  const c = z.string().default("asdf").pipe(z.string());
  expect(c._zod.optin).toEqual("optional");
  expect(c._zod.optout).toEqual(undefined);

  const d = z
    .string()
    .transform((val) => (Math.random() ? val : undefined))
    .pipe(z.string().default("asdf"));
  expect(d._zod.optin).toEqual(undefined);
  expect(d._zod.optout).toEqual(undefined);
});

test("pipe optionality inside objects", () => {
  const schema = z.object({
    a: z.string().optional(),
    b: z.string().optional().pipe(z.string()),
    c: z.string().default("asdf").pipe(z.string()),
    d: z
      .string()
      .transform((val) => (Math.random() ? val : undefined))
      .pipe(z.string().optional()),
    e: z
      .string()
      .transform((val) => (Math.random() ? val : undefined))
      .pipe(z.string().default("asdf")),
  });

  type SchemaIn = z.input<typeof schema>;
  expectTypeOf<SchemaIn>().toEqualTypeOf<{
    a?: string | undefined;
    b?: string | undefined;
    c?: string | undefined;
    d: string;
    e: string;
  }>();

  type SchemaOut = z.output<typeof schema>;
  expectTypeOf<SchemaOut>().toEqualTypeOf<{
    a?: string | undefined;
    b: string;
    c: string;
    d?: string | undefined;
    e: string;
  }>();
});

test("optional prop with pipe", () => {
  const schema = z.object({
    id: z
      .union([z.number(), z.string().nullish()])
      .transform((val) => (val === null || val === undefined ? val : Number(val)))
      .pipe(z.number())
      .optional(),
  });

  schema.parse({});
  schema.parse({}, { jitless: true });
});

// exactOptional tests
test(".exactOptional()", () => {
  const schema = z.string().exactOptional();
  expect(schema.parse("asdf")).toEqual("asdf");
  expect(schema.safeParse(undefined).success).toEqual(false);
  expect(schema.safeParse(null).success).toEqual(false);

  // Type should NOT include undefined
  expectTypeOf<typeof schema._output>().toEqualTypeOf<string>();
  expectTypeOf<typeof schema._input>().toEqualTypeOf<string>();
});

test("exactOptional unwrap", () => {
  const unwrapped = z.string().exactOptional().unwrap();
  expect(unwrapped).toBeInstanceOf(z.ZodString);
});

test("exactOptional optionality", () => {
  const a = z.string().exactOptional();
  expect(a._zod.optin).toEqual("optional");
  expect(a._zod.optout).toEqual("optional");
  expectTypeOf<typeof a._zod.optin>().toEqualTypeOf<"optional">();
  expectTypeOf<typeof a._zod.optout>().toEqualTypeOf<"optional">();
});

test("exactOptional in objects - absent keys", () => {
  const schema = z.object({
    a: z.string().exactOptional(),
  });

  // Absent key should pass
  expect(schema.parse({})).toEqual({});
  expect(schema.parse({}, { jitless: true })).toEqual({});

  // Present key with valid value should pass
  expect(schema.parse({ a: "hello" })).toEqual({ a: "hello" });
  expect(schema.parse({ a: "hello" }, { jitless: true })).toEqual({ a: "hello" });
});

test("exactOptional in objects - explicit undefined rejected", () => {
  const schema = z.object({
    a: z.string().exactOptional(),
  });

  // Explicit undefined should fail
  expect(schema.safeParse({ a: undefined }).success).toEqual(false);
  expect(schema.safeParse({ a: undefined }, { jitless: true }).success).toEqual(false);
});

test("exactOptional type inference in objects", () => {
  const schema = z.object({
    a: z.string().exactOptional(),
    b: z.string().optional(),
  });

  type SchemaIn = z.input<typeof schema>;
  expectTypeOf<SchemaIn>().toEqualTypeOf<{
    a?: string;
    b?: string | undefined;
  }>();

  type SchemaOut = z.output<typeof schema>;
  expectTypeOf<SchemaOut>().toEqualTypeOf<{
    a?: string;
    b?: string | undefined;
  }>();
});

test("exactOptional vs optional comparison", () => {
  const optionalSchema = z.object({ a: z.string().optional() });
  const exactOptionalSchema = z.object({ a: z.string().exactOptional() });

  // Both accept absent keys
  expect(optionalSchema.parse({})).toEqual({});
  expect(exactOptionalSchema.parse({})).toEqual({});

  // Both accept valid values
  expect(optionalSchema.parse({ a: "hi" })).toEqual({ a: "hi" });
  expect(exactOptionalSchema.parse({ a: "hi" })).toEqual({ a: "hi" });

  // optional() accepts explicit undefined
  expect(optionalSchema.parse({ a: undefined })).toEqual({ a: undefined });

  // exactOptional() rejects explicit undefined
  expect(exactOptionalSchema.safeParse({ a: undefined }).success).toEqual(false);
});
