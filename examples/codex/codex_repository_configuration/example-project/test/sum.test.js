import assert from "node:assert/strict";
import test from "node:test";

import { sum } from "../src/sum.js";

test("adds finite numbers", () => {
  assert.equal(sum(2, 3), 5);
});

test("rejects non-finite input", () => {
  assert.throws(() => sum(Number.POSITIVE_INFINITY, 1), {
    name: "TypeError",
    message: "sum expects two finite numbers",
  });
});
