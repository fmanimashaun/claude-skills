// WHERE THE QA ROBOT READS THE MAIL THE APP SENT (qa-flow #1835, lifted from Retask #826). A real sign-in ends in an email —
// a code after a password, or a one-time link — and the robot can walk that flow only by reading it.
//
// ONLY A LOCAL CATCHER. Mail is caught by something the robot runs (Mailpit, started beside the release image); there is
// no reader for a real mailbox and none is planned. So the catcher's own URL goes through the same local-target guard as
// the app, and an address not of the QA marker's shape is refused BEFORE any request is made.
//
// NOTHING HERE MINTS A SESSION or reaches into the app's database: it reads mail that was really sent.
// One interface, `MailReader`, so a sign-in helper never knows which catcher it reads. Mailpit is the one shipped; a
// second (for example a framework's file-based dev mailer) is added when a project needs it.
import { assertLocalTarget } from "./local-target.ts";
import { assertQaAddress } from "./qa-marker.ts";

export type Mail = { id: string; to: string[]; subject: string; text: string; html: string; at: Date };

export type MailQuery = {
  /** Drop what an earlier run or step left behind: take `const t = new Date()` BEFORE the action, then pass it. */
  since?: Date;
  subject?: RegExp;
  /** A further test on the whole message, for example "carries a sign-in link". */
  match?: (mail: Mail) => boolean;
};

export interface MailReader {
  /** Every message to `address` that matches, oldest first. */
  messagesTo(address: string, query?: MailQuery): Promise<Mail[]>;
}

function keep(mails: Mail[], query: MailQuery): Mail[] {
  return mails
    .filter(m => !query.since || m.at.getTime() >= query.since.getTime() - 1000)
    .filter(m => !query.subject || query.subject.test(m.subject))
    .filter(m => !query.match || query.match(m))
    .sort((a, b) => a.at.getTime() - b.at.getTime());
}

/** The newest matching message, polling until it arrives (a background job delivers it). Fails naming what it waited for. */
export async function waitForMailTo(
  reader: MailReader,
  address: string,
  query: MailQuery & { timeoutMs?: number; intervalMs?: number } = {},
): Promise<Mail> {
  const { timeoutMs = 15_000, intervalMs = 500, ...rest } = query;
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const found = (await reader.messagesTo(address, rest)).at(-1);
    if (found) return found;
    if (Date.now() >= deadline) {
      throw new Error(`no email to ${address}${rest.subject ? ` matching ${rest.subject}` : ""}` +
        `${rest.since ? ` since ${rest.since.toISOString()}` : ""} within ${timeoutMs} ms`);
    }
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }
}

type MailpitSummary = { ID: string; Created: string; Subject: string; To: { Address: string }[] };
type MailpitMessage = { ID: string; Subject: string; Text?: string; HTML?: string };

export class MailpitReader implements MailReader {
  private readonly baseUrl: string;
  private readonly fetcher: typeof fetch;

  constructor(baseUrl = "http://127.0.0.1:8025", fetcher: typeof fetch = fetch) {
    this.baseUrl = assertLocalTarget(baseUrl);
    this.fetcher = fetcher;
  }

  private async json<T>(path: string): Promise<T> {
    const res = await this.fetcher(`${this.baseUrl}${path}`);
    if (!res.ok) throw new Error(`Mailpit answered ${res.status} for ${path}`);
    return (await res.json()) as T;
  }

  async messagesTo(address: string, query: MailQuery = {}): Promise<Mail[]> {
    const want = assertQaAddress(address, "read the mail of");
    const found = await this.json<{ messages?: MailpitSummary[] }>(`/api/v1/search?query=${encodeURIComponent(`to:${want}`)}&limit=50`);
    const summaries = (found.messages ?? []).filter(s => s.To.some(t => t.Address.toLowerCase() === want));
    const mails = await Promise.all(summaries.map(async (s): Promise<Mail> => {
      const full = await this.json<MailpitMessage>(`/api/v1/message/${encodeURIComponent(s.ID)}`);
      return {
        id: s.ID,
        to: s.To.map(t => t.Address.toLowerCase()),
        subject: s.Subject,
        text: full.Text ?? "",
        html: full.HTML ?? "",
        at: new Date(s.Created),
      };
    }));
    return keep(mails, query);
  }
}

/** QA_MAIL=mailpit (QA_MAILPIT_URL, default http://127.0.0.1:8025). Anything else fails and says what is valid. */
export function mailReaderFromEnv(env: Record<string, string | undefined> = process.env): MailReader {
  const kind = (env.QA_MAIL ?? "").trim();
  if (kind === "mailpit") return new MailpitReader(env.QA_MAILPIT_URL?.trim() || undefined);
  throw new Error(`QA_MAIL must be "mailpit" (got ${JSON.stringify(env.QA_MAIL ?? null)})`);
}

/**
 * The six-digit code that follows the word "code" (any case) in a message. Throws naming the subject otherwise. There is
 * deliberately no "first six digits" fallback: a postcode or an order number must never be typed into a second-factor box.
 */
export function codeInMail(mail: Mail): string {
  const code = mail.text.match(/\bcode\b\D{0,20}?(\d{6})\b/i)?.[1];
  if (!code) throw new Error(`no six-digit code after "code" in "${mail.subject}"`);
  return code;
}

/**
 * The first link in a message whose PATH matches `pathPattern` (your app's sign-in link route), rebased onto `baseURL`.
 * Mail links name the host the app was configured with, often production, so only the path is kept — the robot then
 * follows it on the local stack. `baseURL` goes through the local-target guard.
 */
export function linkInMail(mail: Mail, baseURL: string, pathPattern: RegExp): string | null {
  const origin = assertLocalTarget(baseURL);
  for (const raw of `${mail.text}\n${mail.html}`.match(/https?:\/\/[^\s"'<>)]+/g) ?? []) {
    let url: URL;
    try { url = new URL(raw); } catch { continue; }
    if (pathPattern.test(url.pathname)) return `${origin}${url.pathname}${url.search}`;
  }
  return null;
}
