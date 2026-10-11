// THE ONE ALLOW-LIST FOR "A THROWAWAY STACK ON THIS MACHINE" (qa-flow #1835, lifted from Retask #826). The release-image
// QA robot signs real accounts in and creates records, so it must never be pointed at a real system. A check on the URL's
// TEXT is not enough: `https://127.0.0.1:x@prod.example.com/` starts with a loopback address and dials the production host,
// because everything before the `@` is userinfo. So the URL is PARSED, and the hostname it will actually dial is judged
// against a short list, with no userinfo at all. A prefix or glob check (`127.*`, `localhost*`) was bypassed in review.
//
// Call it from EVERY entry point: the runner, the config load, globalSetup, each sign-in helper, the mail reader, teardown.
const LOCAL_HOSTS: ReadonlySet<string> = new Set(["127.0.0.1", "localhost", "[::1]"]);

/** The origin of `raw` when it is plain http(s) to this machine; throws, saying why, otherwise. */
export function assertLocalTarget(raw: string | undefined): string {
  let url: URL;
  try {
    url = new URL(String(raw ?? ""));
  } catch {
    throw new Error(`refusing "${raw ?? ""}": not a URL (the QA robot runs only against a stack on this machine)`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error(`refusing ${url.protocol}// target "${raw}": http or https only`);
  }
  if (url.username || url.password) {
    throw new Error(`refusing "${raw}": a URL with userinfo (user:password@) is not accepted; the host it names is ${url.hostname}`);
  }
  if (!LOCAL_HOSTS.has(url.hostname)) {
    throw new Error(`refusing "${raw}": ${url.hostname} is not this machine (allowed: 127.0.0.1, localhost, ::1)`);
  }
  return url.origin;
}
