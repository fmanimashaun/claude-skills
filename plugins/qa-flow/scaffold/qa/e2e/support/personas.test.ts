import { test } from "node:test";
import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { personaState, readPersonas, readRecords, recordCreated, seedDir, writePersonas } from "./personas.ts";

const tmp = () => mkdtempSync(join(tmpdir(), "qa-seed-"));
const ADMIN = { handle: "admin", role: "admin", email: "qa+admin@example.com", state: "/s/admin.json" };

test("personas: written, read back, and a persona's state found by handle; files are owner-only", () => {
  const d = tmp();
  writePersonas({ domain: "example.com", personas: [ADMIN] }, d);
  assert.equal(personaState("admin", d), "/s/admin.json");
  assert.equal(readPersonas(d)?.personas.length, 1);
  assert.equal(statSync(join(d, "personas.json")).mode & 0o777, 0o600);
});

test("personas: a non-QA address is refused on write AND on read (a hand-edited manifest)", () => {
  const d = tmp();
  assert.throws(() => writePersonas({ domain: "example.com", personas: [{ ...ADMIN, email: "alice@example.com" }] }, d),
    /refusing to record the persona "alice@example.com"/);
  writeFileSync(join(d, "personas.json"), JSON.stringify({ domain: "x", personas: [{ ...ADMIN, email: "alice@example.com" }] }));
  assert.throws(() => readPersonas(d), /refusing to record the persona/);
});

test("records: a hand-edited records.json with a non-QA author, or no id, is refused on read", () => {
  const d = tmp();
  writeFileSync(join(d, "records.json"), JSON.stringify([{ kind: "client", id: "c1", by: "alice@example.com" }]));
  assert.throws(() => readRecords(d), /refusing to record a record made by "alice@example.com"/);
  writeFileSync(join(d, "records.json"), JSON.stringify([{ kind: "client", by: "qa+admin@example.com" }]));
  assert.throws(() => readRecords(d), /needs a kind and an id/);
});

test("manifests: an existing WIDER file is narrowed to owner-only on overwrite (mode applies only on create)", () => {
  const d = tmp();
  writeFileSync(join(d, "personas.json"), "{}"); chmodSync(join(d, "personas.json"), 0o644);
  writePersonas({ domain: "example.com", personas: [ADMIN] }, d);
  assert.equal(statSync(join(d, "personas.json")).mode & 0o777, 0o600);
  writeFileSync(join(d, "records.json"), "[]"); chmodSync(join(d, "records.json"), 0o666);
  recordCreated({ kind: "client", id: "c1", by: "qa+admin@example.com" }, d);
  assert.equal(statSync(join(d, "records.json")).mode & 0o777, 0o600);
});

test("records: a new records.json is created owner-only", () => {
  const d = tmp();
  recordCreated({ kind: "client", id: "c1", by: "qa+admin@example.com" }, d);
  assert.equal(statSync(join(d, "records.json")).mode & 0o777, 0o600);
});

test("personas: a duplicate handle is refused", () => {
  assert.throws(() => writePersonas({ domain: "example.com", personas: [ADMIN, ADMIN] }, tmp()), /appears twice/);
});

test("personas: an unknown persona names what to run", () => {
  assert.throws(() => personaState("ghost", tmp()), /no QA persona "ghost".*run the seed/);
});

test("records: appended in order; a record made by a non-QA address, or without kind/id, is refused", () => {
  const d = tmp();
  recordCreated({ kind: "client", id: "c1", by: "qa+admin@example.com" }, d);
  recordCreated({ kind: "request", id: "r1", by: "qa+admin@example.com" }, d);
  assert.deepEqual(readRecords(d).map(r => r.id), ["c1", "r1"]);
  assert.throws(() => recordCreated({ kind: "client", id: "c2", by: "alice@example.com" }, d), /refusing to record a record made by/);
  assert.throws(() => recordCreated({ kind: " ", id: "c3", by: "qa+admin@example.com" }, d), /needs a kind and an id/);
  assert.equal(readRecords(d).length, 2);
});

test("seedDir: QA_SEED_DIR wins, else qa/.qa-seed", () => {
  assert.equal(seedDir({ QA_SEED_DIR: "/x/y" }), "/x/y");
  assert.match(seedDir({}), /qa[\\/]\.qa-seed$/);
});
