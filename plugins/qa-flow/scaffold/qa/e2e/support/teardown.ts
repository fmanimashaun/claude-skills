// THE PROVING TEARDOWN (qa-flow #1836, lifted from Retask #826). The QA accounts and records live only in the throwaway stack's own
// database, so tearing down is the stack's own `down` (which deletes its volumes). That is a hope until it is READ BACK: this asks docker
// what is still there under the stack's name and fails if anything is. And the read-back must be able to fail: a docker that cannot be
// asked (not running, not on PATH) is NOT "nothing left" — Retask's first version turned `docker ... | grep -c ... || true` into "0".
import { spawnSync } from "node:child_process";

export type Run = (cmd: string, args: string[]) => { status: number | null; stdout: string; stderr: string; error?: Error };

const realRun: Run = (cmd, args) => {
  const r = spawnSync(cmd, args, { encoding: "utf8", timeout: 60_000 });
  return { status: r.status, stdout: r.stdout ?? "", stderr: r.stderr ?? "", error: r.error };
};

/** Names from a docker listing, or a throw naming why docker could not be asked. Never an empty list for a failed query. */
function ask(run: Run, args: string[]): string[] {
  const r = run("docker", args);
  if (r.error || r.status !== 0) {
    throw new Error(`teardown cannot prove the stack is gone: \`docker ${args.join(" ")}\` failed` +
      ` (${r.error ? r.error.message : `exit ${r.status}`}${r.stderr.trim() ? `: ${r.stderr.trim().slice(0, 200)}` : ""})`);
  }
  return r.stdout.split("\n").map(s => s.trim()).filter(Boolean);
}

/**
 * Throws unless no container and no volume whose name starts with `${stack}-` or `${stack}_` (compose's two separators), or equals
 * `stack`, is left. `stack` is the compose project name: a plain name, so a regex or glob character is refused, not interpreted.
 */
export function proveNothingLeft(stack: string, run: Run = realRun): void {
  if (!/^[a-z0-9][a-z0-9_-]*$/.test(stack)) throw new Error(`refusing stack name ${JSON.stringify(stack)}: lower-case letters, digits, - and _ only`);
  const ours = (name: string) => name === stack || name.startsWith(`${stack}-`) || name.startsWith(`${stack}_`);
  const containers = ask(run, ["ps", "-a", "--format", "{{.Names}}"]).filter(ours);
  const volumes = ask(run, ["volume", "ls", "--format", "{{.Name}}"]).filter(ours);
  if (containers.length || volumes.length) {
    throw new Error(`teardown left ${containers.length} container(s) and ${volumes.length} volume(s) of ${stack}: ` +
      [...containers, ...volumes].slice(0, 10).join(", "));
  }
}
