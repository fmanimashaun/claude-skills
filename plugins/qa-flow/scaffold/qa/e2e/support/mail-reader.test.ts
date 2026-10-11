import { test } from "node:test";
import assert from "node:assert/strict";
import { MailpitReader, codeInMail, linkInMail, mailReaderFromEnv, waitForMailTo, type Mail, type MailReader } from "./mail-reader.ts";

function fakeMailpit(messages: Array<{ id: string; to: string; subject: string; text: string; created: string }>) {
  const calls: string[] = [];
  const fetcher = (async (input: string | URL | Request) => {
    const url = String(input);
    calls.push(url);
    const path = new URL(url).pathname;
    if (path === "/api/v1/search") {
      const to = decodeURIComponent(new URL(url).searchParams.get("query") ?? "").replace(/^to:/, "");
      const hits = messages.filter(m => m.to === to).map(m => ({ ID: m.id, Created: m.created, Subject: m.subject, To: [{ Address: m.to }] }));
      return new Response(JSON.stringify({ messages: hits }), { status: 200 });
    }
    const m = messages.find(x => path === `/api/v1/message/${x.id}`);
    return m ? new Response(JSON.stringify({ ID: m.id, Subject: m.subject, Text: m.text }), { status: 200 })
             : new Response("{}", { status: 404 });
  }) as typeof fetch;
  return { fetcher, calls };
}

const MAILS = [
  { id: "2", to: "qa+admin@example.com", subject: "Your code", text: "Code: 123456", created: "2026-10-10T10:00:05Z" },
  { id: "1", to: "qa+admin@example.com", subject: "Welcome", text: "hi", created: "2026-10-10T10:00:00Z" },
];

test("mail-reader: a non-QA address is refused BEFORE any request is made", async () => {
  const { fetcher, calls } = fakeMailpit(MAILS);
  const reader = new MailpitReader("http://127.0.0.1:8025", fetcher);
  await assert.rejects(reader.messagesTo("alice@example.com"), /refusing to read the mail of/);
  assert.equal(calls.length, 0);
});

test("mail-reader: the catcher itself must be on this machine (no real mailbox)", () => {
  assert.throws(() => new MailpitReader("https://mail.example.com"), /is not this machine/);
  assert.throws(() => new MailpitReader("http://127.0.0.1:8025@mail.example.com"), /userinfo/);
});

test("mail-reader: messages to the address, oldest first, filtered by subject and since", async () => {
  const reader = new MailpitReader("http://127.0.0.1:8025", fakeMailpit(MAILS).fetcher);
  assert.deepEqual((await reader.messagesTo("qa+admin@example.com")).map(m => m.id), ["1", "2"]);
  assert.deepEqual((await reader.messagesTo("qa+admin@example.com", { subject: /code/i })).map(m => m.id), ["2"]);
  assert.deepEqual((await reader.messagesTo("qa+admin@example.com", { since: new Date("2026-10-10T10:00:04Z") })).map(m => m.id), ["2"]);
});

test("mail-reader: a message the catcher returns for ANOTHER recipient is dropped (exact-recipient filter)", async () => {
  // A catcher whose search is looser than asked (a substring match, a different query syntax) must not leak a stranger's mail.
  const loose = (async (input: string | URL | Request) => {
    const path = new URL(String(input)).pathname;
    if (path === "/api/v1/search") {
      return new Response(JSON.stringify({ messages: [
        { ID: "f", Created: "2026-10-10T10:00:00Z", Subject: "Reset", To: [{ Address: "qa+admin@example.com.attacker.test" }] },
        { ID: "m", Created: "2026-10-10T10:00:01Z", Subject: "Code", To: [{ Address: "qa+admin@example.com" }] },
      ] }), { status: 200 });
    }
    return new Response(JSON.stringify({ ID: path.split("/").pop(), Subject: "x", Text: "t" }), { status: 200 });
  }) as typeof fetch;
  const got = await new MailpitReader("http://127.0.0.1:8025", loose).messagesTo("qa+admin@example.com");
  assert.deepEqual(got.map(m => m.id), ["m"]);
});

test("mail-reader: waitForMailTo returns the newest, and fails naming what it waited for", async () => {
  const reader = new MailpitReader("http://127.0.0.1:8025", fakeMailpit(MAILS).fetcher);
  assert.equal((await waitForMailTo(reader, "qa+admin@example.com")).id, "2");
  const empty: MailReader = { messagesTo: async () => [] };
  await assert.rejects(waitForMailTo(empty, "qa+none@example.com", { subject: /code/, timeoutMs: 30, intervalMs: 10 }),
    /no email to qa\+none@example\.com matching \/code\/ within 30 ms/);
});

test("mail-reader: only QA_MAIL=mailpit is accepted", () => {
  assert.throws(() => mailReaderFromEnv({ QA_MAIL: "imap" }), /QA_MAIL must be "mailpit"/);
  assert.throws(() => mailReaderFromEnv({}), /QA_MAIL must be "mailpit"/);
  assert.ok(mailReaderFromEnv({ QA_MAIL: "mailpit" }) instanceof MailpitReader);
});

const mail = (text: string, html = ""): Mail => ({ id: "x", to: [], subject: "s", text, html, at: new Date() });

test("mail-reader: the code and the sign-in link are read from the message; the link is rebased onto the local stack", () => {
  assert.equal(codeInMail(mail("Your Code is 654321.")), "654321");
  assert.equal(codeInMail(mail("Ship to 100001. Your code: 654321")), "654321");
  assert.throws(() => codeInMail(mail("no digits")), /no six-digit code/);
  assert.throws(() => codeInMail(mail("Deliver to 100001 by Friday.")), /no six-digit code after "code"/);
  const m = mail("Sign in: https://prod.example.com/login/link/abc123?x=1 thanks");
  assert.equal(linkInMail(m, "http://127.0.0.1:3000", /^\/login\/link\//), "http://127.0.0.1:3000/login/link/abc123?x=1");
  assert.equal(linkInMail(m, "http://127.0.0.1:3000", /^\/magic\//), null);
  assert.throws(() => linkInMail(m, "https://prod.example.com", /^\/login\//), /is not this machine/);
});
