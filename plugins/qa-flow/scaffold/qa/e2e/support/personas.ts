// THE QA PERSONAS AND THE RECORDS THEY MADE (qa-flow #1836, lifted from Retask #826). The seed signs each persona in through the real
// screens (password, then a TOTP from the app's own enrol key, or an emailed code read through the MailReader) and keeps each persona's
// browser state in the seed directory. A spec that wants to be one uses `personaState(handle)` with `test.use({ storageState })`, so no
// session is minted and no app code runs. Every address carries the QA marker; the manifests REFUSE one that does not, on write and on read.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { assertQaAddress } from "./qa-marker.ts";

export type Persona = { handle: string; role: string; email: string; state: string };
export type PersonaManifest = { domain: string; personas: Persona[] };
/** One record the run created, through a screen: what it is, the id the app gave it, and the QA persona that made it. */
export type SeededRecord = { kind: string; id: string; by: string };

/** Where the seed keeps its state: QA_SEED_DIR, else `qa/.qa-seed` under the current directory. Keep it gitignored. */
export const seedDir = (env: Record<string, string | undefined> = process.env): string =>
  resolve(env.QA_SEED_DIR?.trim() || join("qa", ".qa-seed"));

function checked(m: PersonaManifest): PersonaManifest {
  const handles = new Set<string>();
  for (const p of m.personas) {
    assertQaAddress(p.email, "record the persona");
    if (handles.has(p.handle)) throw new Error(`persona "${p.handle}" appears twice in the manifest`);
    handles.add(p.handle);
  }
  return m;
}

export function writePersonas(m: PersonaManifest, dir = seedDir()): void {
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "personas.json"), JSON.stringify(checked(m), null, 2) + "\n", { mode: 0o600 });
}

export function readPersonas(dir = seedDir()): PersonaManifest | null {
  const file = join(dir, "personas.json");
  return existsSync(file) ? checked(JSON.parse(readFileSync(file, "utf8")) as PersonaManifest) : null;
}

/** The browser-state file of a seeded persona, or a failure naming what to run first. */
export function personaState(handle: string, dir = seedDir()): string {
  const persona = readPersonas(dir)?.personas.find(p => p.handle === handle);
  if (!persona) throw new Error(`no QA persona "${handle}" in ${dir}: run the seed against the local stack first`);
  return persona.state;
}

/** Add a record to the records manifest. `by` must be a QA persona's address: a record nobody can attribute to the robot is not ours. */
export function recordCreated(rec: SeededRecord, dir = seedDir()): void {
  assertQaAddress(rec.by, "record a record made by");
  if (!rec.kind.trim() || !rec.id.trim()) throw new Error(`a record needs a kind and an id (got ${JSON.stringify(rec)})`);
  const all = readRecords(dir);
  all.push(rec);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "records.json"), JSON.stringify(all, null, 2) + "\n", { mode: 0o600 });
}

export function readRecords(dir = seedDir()): SeededRecord[] {
  const file = join(dir, "records.json");
  return existsSync(file) ? (JSON.parse(readFileSync(file, "utf8")) as SeededRecord[]) : [];
}
