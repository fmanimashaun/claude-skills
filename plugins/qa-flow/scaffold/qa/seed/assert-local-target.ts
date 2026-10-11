// `node --experimental-strip-types qa/seed/assert-local-target.ts <url>...` (qa-flow #1837, lifted from Retask #826): the shell scripts'
// door to the same allow-list the specs use. Prints each accepted origin; exits 2 naming the first refusal.
import { assertLocalTarget } from "../e2e/support/local-target.ts";

try {
  for (const raw of process.argv.slice(2)) console.log(assertLocalTarget(raw));
} catch (error) {
  console.error(`qa/seed: ${(error as Error).message}`);
  process.exit(2);
}
