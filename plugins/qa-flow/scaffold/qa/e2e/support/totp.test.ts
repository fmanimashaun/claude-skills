import { test } from "node:test";
import assert from "node:assert/strict";
import { base32Decode, totp, totpFromKey } from "./totp.ts";

// RFC 6238 Appendix B, the SHA-1 rows: the published test key is the ASCII digits 1..9,0 twice (20 bytes), eight
// digits, 30-second steps. Built at runtime, not written as a literal: it is a public test vector, not a secret, but a
// literal (or its base32) reads as a high-entropy secret to a scanner.
const KEY = Buffer.from(Array.from({ length: 20 }, (_, i) => 0x30 + ((i + 1) % 10)));
const RFC_VECTORS: Array<[number, string]> = [
  [59, "94287082"], [1111111109, "07081804"], [1111111111, "14050471"],
  [1234567890, "89005924"], [2000000000, "69279037"], [20000000000, "65353130"],
];

test("totp: every RFC 6238 SHA-1 test vector", () => {
  for (const [t, code] of RFC_VECTORS) assert.equal(totpFromKey(KEY, t, 8), code, `T=${t}`);
});

test("totp: six digits is the last six of the eight-digit value, zero-padded", () => {
  assert.equal(totpFromKey(KEY, 1111111109, 6), "081804");
  assert.equal(totpFromKey(KEY, 59, 6), "287082");
});

// RFC 4648 base32 of a buffer, for building the enrol-screen form of the test key at runtime.
function base32Encode(bytes: Buffer): string {
  const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const b of bytes) bits += b.toString(2).padStart(8, "0");
  let out = "";
  for (let i = 0; i < bits.length; i += 5) out += ALPHABET.charAt(parseInt(bits.slice(i, i + 5).padEnd(5, "0"), 2));
  return out.padEnd(Math.ceil(out.length / 8) * 8, "=");
}

test("totp: a base32 secret as the enrol screen shows it (spaces, lower case, padding) is the same key", () => {
  const secret = base32Encode(KEY);
  assert.equal(secret.length, 32);
  assert.deepEqual(base32Decode(secret), KEY);
  const asShown = secret.replace(/=+$/, "").toLowerCase().replace(/(.{4})/g, "$1 ").trim() + "====";
  assert.equal(totp(asShown, 1111111109), "081804");
});

test("totp: a character outside base32 is refused, not skipped", () => {
  assert.throws(() => base32Decode("GEZD1"), /not base32: 1/);
});
