/** Add two finite numbers. */
export function sum(left, right) {
  if (!Number.isFinite(left) || !Number.isFinite(right)) {
    throw new TypeError("sum expects two finite numbers");
  }

  return left + right;
}
