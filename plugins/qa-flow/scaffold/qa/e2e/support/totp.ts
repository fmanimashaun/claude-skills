// A TOTP CODE, the way an authenticator app makes it (qa-flow #1835, lifted from Retask #826): RFC 6238 over HMAC-SHA1,
// six digits, thirty-second steps — the parameters most Rails TOTP setups use. The robot computes it from the app's OWN
// enrolment key, shown on the enrol screen, so sign-in goes through the real second factor. Node's crypto, no dependency.
import { createHmac } from "node:crypto";

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

/** RFC 4648 base32, as an enrolment screen shows a secret: spaces, hyphens and `=` padding allowed, any case. */
export function base32Decode(input: string): Buffer {
  const clean = input.replace(/[\s=-]/g, "").toUpperCase();
  let bits = "";
  for (const c of clean) {
    const i = ALPHABET.indexOf(c);
    if (i < 0) throw new Error(`not base32: ${c}`);
    bits += i.toString(2).padStart(5, "0");
  }
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}

/** The code for a raw `key` at `atSeconds`: RFC 6238 §4 with RFC 4226 §5.3 truncation. `digits` defaults to 6. */
export function totpFromKey(key: Buffer, atSeconds: number, digits = 6, stepSeconds = 30): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(atSeconds / stepSeconds)));
  const mac = createHmac("sha1", key).update(counter).digest();
  const offset = mac.readUInt8(mac.length - 1) & 0x0f;
  const binary = mac.readUInt32BE(offset) & 0x7fffffff;
  return String(binary % 10 ** digits).padStart(digits, "0");
}

/** The six-digit code for a base32 `secret` (as the enrolment screen shows it) at `atSeconds` (default now). */
export function totp(secret: string, atSeconds: number = Math.floor(Date.now() / 1000)): string {
  return totpFromKey(base32Decode(secret), atSeconds);
}
