// A SECOND DOOR (qa-flow #1837, lifted from Retask #826): Playwright's globalSetup, for a run that did not come through qa/seed/image-e2e.
// Point `globalSetup` at this file in the image project's config. It refuses to start against anything but this machine.
import { assertLocalTarget } from "../e2e/support/local-target.ts";

export default async function globalSetup(): Promise<void> {
  assertLocalTarget(process.env.QA_BASE_URL);
  if (process.env.QA_MAILPIT_URL) assertLocalTarget(process.env.QA_MAILPIT_URL);
}
