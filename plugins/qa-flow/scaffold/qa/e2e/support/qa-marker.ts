// WHAT MAKES AN ACCOUNT RECOGNISABLY QA-ONLY (qa-flow #1835, lifted from Retask #826): its address, `qa+<handle>@<domain>`.
// Every account the robot creates carries it, teardown looks for it, and the sign-in helpers and mail readers REFUSE any
// address not of that shape — a helper that can be pointed at a person's account or a real inbox is what this robot must
// never be. It checks the address SHAPE, not the domain — `qa+x@` any domain passes, so use a domain you own — and it is
// the local-target guard and the local mail catcher, not this check, that keep the robot off real systems and inboxes.
const QA_ADDRESS = /^qa\+[a-z0-9][a-z0-9._-]{0,40}@[a-z0-9.-]+\.[a-z]{2,}$/i;

export const isQaAddress = (address: string): boolean => QA_ADDRESS.test(address.trim());

export function qaAddress(handle: string, domain: string): string {
  const address = `qa+${handle.trim().toLowerCase()}@${domain.trim().toLowerCase()}`;
  if (!isQaAddress(address)) throw new Error(`"${address}" is not a valid QA address (qa+<handle>@<domain>)`);
  return address;
}

/** `action` finishes "refusing to …": the sign-in helpers say "sign in as", the mail readers "read the mail of". */
export function assertQaAddress(address: string, action = "sign in as"): string {
  if (!isQaAddress(address)) throw new Error(`refusing to ${action} "${address}": QA accounts are qa+<handle>@<domain>`);
  return address.trim().toLowerCase();
}
