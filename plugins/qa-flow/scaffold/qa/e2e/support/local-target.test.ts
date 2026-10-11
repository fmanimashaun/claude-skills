import { test } from "node:test";
import assert from "node:assert/strict";
import { assertLocalTarget } from "./local-target.ts";

test("local-target: this machine is accepted, as its origin", () => {
  assert.equal(assertLocalTarget("http://127.0.0.1:3000/login"), "http://127.0.0.1:3000");
  assert.equal(assertLocalTarget("https://localhost:8443"), "https://localhost:8443");
  assert.equal(assertLocalTarget("http://[::1]:3000/"), "http://[::1]:3000");
});

test("local-target: userinfo that hides a real host is refused (the loopback-prefix bypass)", () => {
  assert.throws(() => assertLocalTarget("https://127.0.0.1:x@prod.example.com/"), /userinfo/);
  assert.throws(() => assertLocalTarget("http://localhost@prod.example.com"), /userinfo/);
});

test("local-target: a host that only STARTS like this machine is refused (prefix and glob checks were bypassed)", () => {
  for (const raw of ["http://127.0.0.1.prod.example.com", "http://localhost.example.com", "http://127.0.0.10:3000",
                     "http://localhostx:3000", "http://0.0.0.0:3000", "http://prod.example.com/?127.0.0.1"]) {
    assert.throws(() => assertLocalTarget(raw), /is not this machine/, raw);
  }
});

test("local-target: not http(s), not a URL, or missing is refused", () => {
  assert.throws(() => assertLocalTarget("file:///etc/passwd"), /http or https only/);
  assert.throws(() => assertLocalTarget("javascript:alert(1)"), /http or https only/);
  assert.throws(() => assertLocalTarget("127.0.0.1:3000"), /http or https only|not a URL/);
  assert.throws(() => assertLocalTarget(undefined), /not a URL/);
  assert.throws(() => assertLocalTarget(""), /not a URL/);
});
