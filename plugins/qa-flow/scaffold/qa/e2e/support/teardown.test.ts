import { test } from "node:test";
import assert from "node:assert/strict";
import { proveNothingLeft, type Run } from "./teardown.ts";

const docker = (containers: string[], volumes: string[]): Run => (_cmd, args) =>
  ({ status: 0, stderr: "", stdout: (args[0] === "ps" ? containers : volumes).join("\n") + "\n" });

test("teardown: nothing of the stack left passes; another project's names do not count", () => {
  proveNothingLeft("myapp-certify", docker(["other-db", "xmyapp-certify-web", "myapp-certifyx"], ["other_data"]));
});

test("teardown: a leftover container or volume of the stack FAILS, naming it", () => {
  assert.throws(() => proveNothingLeft("myapp-certify", docker(["myapp-certify-web-1"], [])), /1 container\(s\) and 0 volume\(s\).*myapp-certify-web-1/);
  assert.throws(() => proveNothingLeft("myapp-certify", docker([], ["myapp-certify_pgdata"])), /0 container\(s\) and 1 volume\(s\).*myapp-certify_pgdata/);
  assert.throws(() => proveNothingLeft("myapp-certify", docker(["myapp-certify"], [])), /1 container/);
});

test("teardown: docker that cannot be asked FAILS CLOSED — never read as nothing left", () => {
  const down: Run = () => ({ status: 1, stdout: "", stderr: "Cannot connect to the Docker daemon" });
  assert.throws(() => proveNothingLeft("myapp-certify", down), /cannot prove the stack is gone.*exit 1.*Cannot connect/);
  const missing: Run = () => ({ status: null, stdout: "", stderr: "", error: new Error("spawnSync docker ENOENT") });
  assert.throws(() => proveNothingLeft("myapp-certify", missing), /cannot prove the stack is gone.*ENOENT/);
  let n = 0;
  const volumesFail: Run = (_c, args) => (n++, args[0] === "ps" ? { status: 0, stdout: "", stderr: "" } : { status: 125, stdout: "", stderr: "boom" });
  assert.throws(() => proveNothingLeft("myapp-certify", volumesFail), /volume ls.*exit 125/);
  assert.equal(n, 2);
});

test("teardown: a stack name that is not a plain name is refused, not used as a pattern", () => {
  for (const bad of ["", "*", "my.app", "MyApp", "-x", "a b"]) assert.throws(() => proveNothingLeft(bad, docker([], [])), /refusing stack name/, bad);
});
