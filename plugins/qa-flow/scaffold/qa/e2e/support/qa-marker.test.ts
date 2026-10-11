import { test } from "node:test";
import assert from "node:assert/strict";
import { assertQaAddress, isQaAddress, qaAddress } from "./qa-marker.ts";

test("qa-marker: qa+<handle>@<domain> is a QA address, normalised", () => {
  assert.equal(qaAddress(" Admin ", "Example.COM"), "qa+admin@example.com");
  assert.equal(assertQaAddress(" QA+staff.1@example.com "), "qa+staff.1@example.com");
});

test("qa-marker: a person's address, or one that only contains the marker, is refused", () => {
  for (const a of ["alice@example.com", "xqa+admin@example.com", "qa+@example.com", "qa+admin@localhost",
                   "qa+admin@example.com, alice@example.com", "qa+admin@example.com\nbcc:alice@example.com"]) {
    assert.equal(isQaAddress(a), false, a);
    assert.throws(() => assertQaAddress(a, "read the mail of"), /refusing to read the mail of/, a);
  }
});
