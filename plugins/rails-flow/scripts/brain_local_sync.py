#!/usr/bin/env python3
"""brain_local_sync.py -- the bridge between the repo brain and Claude Code's per-machine memory (#877).

Two stores, one shape, no wire between them:

  docs/brain/memos/<type>/<slug>.md    the project's memory: committed, reviewed, the team's truth
                                       (a memo at the brain ROOT is legacy: read, and reported misplaced)
  ~/.claude/projects/<slug>/memory/    Claude Code's auto-memory: per machine, per user, uncommitted;
                                       its MEMORY.md index is what a session loads at start

  --status    counts in each direction; --brief prints the one line the SessionStart hook shows
  --pull      brain -> local: for every memo with no local counterpart, a POINTER memory whose
              description is the memo's own line verbatim and whose body names the repo file; one
              index line. Prints the plan; --write applies it. Idempotent; never overwrites a file it
              did not write.
  --propose   local -> brain: every local `feedback`/`project` memory with no brain counterpart,
              printed as the memo file it would become, body VERBATIM. Writes nothing -- the repo is
              reviewed truth, and a local memory may be personal. `/rails-flow:brain` writes.

Never in either direction: `user` memories (who the person is). `reference` memories are listed
and not proposed (URLs and tickets belong in STATUS.md / DECISIONS.md, not memos). No paraphrase, no
compression, no model in the loop: every byte that crosses is a verbatim body or the author's own
description line, so the output is a function of the inputs.

Exit 0 normally; 3 when there is no brain or no auto-memory store for this path (not applicable is
not "in sync"); 2 on unreadable input.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

BRAIN = Path("docs/brain")
POINTER_KEY = "brain_pointer"
NEVER_SYNCED = {"user"}                 # personal: belongs to the person, not the project
LISTED_NOT_PROPOSED = {"reference"}
TYPE_TO_MEMO = {"feedback": "feedback", "project": "decision"}
MEMO_TO_LOCAL = {"feedback": "feedback", "decision": "project"}
PREFIX = re.compile(r"^(feedback|decision|project)[-_]")
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", re.S)


# ----------------------------------------------------------------------------- stores

def store_dir(project_root: Path, home: Path) -> Path:
    """The harness's own rule: the project path with every separator turned into `-`, so
    /Users/x/proj -> ~/.claude/projects/-Users-x-proj/memory. Verified against a live store."""
    slug = str(project_root.resolve()).replace("\\", "-").replace("/", "-").replace(":", "-")
    return home / ".claude" / "projects" / slug / "memory"


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        inner = v[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\") if v[0] == '"' else inner
    return v


def _yaml_scalar(v: str) -> str:
    """Plain when YAML allows it; double-quoted (escaped) when the line would otherwise be misread —
    a `: ` inside, a leading quote or `#`, or surrounding whitespace."""
    if v and ": " not in v and " #" not in v and v[0] not in "\"'#&*!|>%@`[]{},-?" and v == v.strip() and not v.endswith(":"):
        return v
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


PROVENANCE_PREFIX = "_Provenance: [observed] — brought from a local Claude memory by"


def core_body(body: str) -> str:
    """The body without the trailer this tool appends when a proposal is accepted, so an accepted
    memo compares equal to the memory it came from instead of reading as diverged forever."""
    lines = body.rstrip("\n").split("\n")
    if lines and lines[-1].startswith(PROVENANCE_PREFIX):
        lines = lines[:-1]
    return "\n".join(lines).strip("\n")


def parse_frontmatter(text: str) -> tuple[dict | None, str]:
    """The YAML subset both stores use: `key: value` lines and ONE level of nesting (`metadata:`)."""
    m = FRONTMATTER.match(text)
    if not m:
        return None, text
    meta: dict = {}
    current: str | None = None
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        if line[0] in " \t":
            if current is not None:
                k, _, v = line.strip().partition(":")
                meta[current][k.strip()] = _unquote(v)
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if v == "":
            meta[k] = {}
            current = k
        else:
            meta[k] = _unquote(v)
            current = None
    return meta, m.group(2)


def key_of(name: str) -> str:
    """`feedback-zsh-word-split` and `zsh-word-split` are the same lesson in two naming conventions."""
    return PREFIX.sub("", name.strip())


MEMOS = BRAIN / "memos"                   # memos/<type>/<slug>.md -- the type is the directory


def memo_path(memo_type: str, slug: str) -> Path:
    return MEMOS / memo_type / f"{slug}.md"


MEMO_SHAPED = re.compile(r"^(feedback|decision)[-_]")   # a root file named like a memo IS a memo, frontmatter or not
UNREADABLE: list[Path] = []               # memo-shaped files the last brain_memos() could not read; reported, never silent


def brain_memos(root: Path) -> list[dict]:
    """Memos under memos/<type>/ (canonical) plus any at the brain root (legacy). A root memo is read
    like any other and carries `misplaced`, the path it belongs at, so --status can say so. A file
    that is memo-shaped -- under memos/, or named feedback_*/decision_* -- but has no frontmatter `name`
    is recorded in UNREADABLE: it is a memo the bridge cannot carry, which is a finding, not silence
    (Retask-platform had one of four, and the first count said three)."""
    out: list[dict] = []
    UNREADABLE.clear()
    d = root / BRAIN
    if not d.is_dir():
        return out
    for p in sorted(d.glob("memos/*/*.md")) + sorted(d.glob("*.md")):
        meta, body = parse_frontmatter(p.read_text(encoding="utf-8"))
        if not meta or "name" not in meta:
            if p.parent != d or MEMO_SHAPED.match(p.name):
                UNREADABLE.append(p)
            continue                      # STATUS.md, MEMORY.md, README.md, the CLAUDE.md history: not memos
        memo_type = p.parent.name if p.parent.parent == d / "memos" else str(meta.get("type", ""))
        at_root = p.parent == d
        out.append({"name": str(meta["name"]), "key": key_of(str(meta["name"])),
                    "description": str(meta.get("description", "")), "type": memo_type,
                    "path": p, "body": body.strip("\n"),
                    "misplaced": (memo_path(memo_type or "feedback", key_of(str(meta["name"]))) if at_root else None)})
    return out


def local_memories(store: Path) -> list[dict]:
    out: list[dict] = []
    if not store.is_dir():
        return out
    for p in sorted(store.glob("*.md")):
        if p.name == "MEMORY.md":
            continue
        meta, body = parse_frontmatter(p.read_text(encoding="utf-8"))
        if not meta or "name" not in meta:
            continue
        md = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
        out.append({"name": str(meta["name"]), "key": key_of(str(meta["name"])),
                    "description": str(meta.get("description", "")),
                    "type": str(md.get("type") or meta.get("type") or ""),
                    "pointer": str(md.get(POINTER_KEY, "")).lower() == "true",
                    "path": p, "body": body.strip("\n")})
    return out


# ----------------------------------------------------------------------------- the plan

def plan(brain: list[dict], local: list[dict]) -> dict:
    by_local = {m["key"]: m for m in local}
    by_brain = {m["key"]: m for m in brain}
    inbound = [m for m in brain if m["key"] not in by_local]
    diverged = []
    for m in brain:
        l = by_local.get(m["key"])
        if l is not None and not l["pointer"] and core_body(l["body"]) != core_body(m["body"]):
            diverged.append((m, l))
    outbound = [l for l in local
                if l["key"] not in by_brain and not l["pointer"]
                and l["type"] in TYPE_TO_MEMO and l["type"] not in NEVER_SYNCED]
    excluded = {t: sum(1 for l in local if l["type"] == t) for t in sorted(NEVER_SYNCED | LISTED_NOT_PROPOSED)}
    misplaced = [m for m in brain if m.get("misplaced")]
    return {"inbound": inbound, "outbound": outbound, "diverged": diverged, "excluded": excluded,
            "misplaced": misplaced, "unreadable": list(UNREADABLE), "brain": len(brain), "local": len(local)}


def pointer_text(memo: dict, rel: str) -> str:
    """The local memory a brain memo becomes: the memo's OWN description (that line is what recall
    matches on), a body that is one pointer, and a marker so the tool recognises its own files."""
    local_type = MEMO_TO_LOCAL.get(memo["type"], "project")
    desc = _yaml_scalar(memo["description"])
    return (f"---\nname: {memo['name']}\ndescription: {desc}\nmetadata:\n  type: {local_type}\n"
            f"  {POINTER_KEY}: true\n  source: {rel}\n---\n\n"
            f"Repo memo: `{rel}`. The repo copy is authoritative; read it before acting on this line.\n")


def index_line(name: str, file: str, description: str) -> str:
    return f"- [{name}]({file}) — {description}\n"


def memo_text(local: dict) -> tuple[str, str, str]:
    """The brain memo a local memory would become. Body VERBATIM; provenance appended, not merged in."""
    memo_type = TYPE_TO_MEMO[local["type"]]
    slug = local["key"]
    rel = memo_path(memo_type, slug).as_posix()
    text = (f"---\nname: {memo_type}-{slug}\ndescription: {_yaml_scalar(local['description'])}\ntype: {memo_type}\n---\n\n"
            f"{local['body']}\n\n{PROVENANCE_PREFIX} "
            f"`/rails-flow:brain-sync local`; body verbatim, {local['path'].name}._\n")
    return rel, text, index_line(f"{memo_type}-{slug}", f"memos/{memo_type}/{slug}.md", local["description"])


# ----------------------------------------------------------------------------- modes

def pull(root: Path, store: Path, p: dict, write: bool) -> dict:
    written, skipped, lines = [], [], []
    store.mkdir(parents=True, exist_ok=True) if write else None
    idx_path = store / "MEMORY.md"
    idx = idx_path.read_text(encoding="utf-8") if idx_path.is_file() else ""
    for memo in p["inbound"]:
        target = store / f"{memo['name']}.md"
        rel = memo["path"].relative_to(root).as_posix()
        if target.exists():
            skipped.append(target)        # NEVER overwrite a file this tool did not write
            continue
        text = pointer_text(memo, rel)
        line = index_line(memo["name"], target.name, memo["description"])
        if write:
            target.write_text(text, encoding="utf-8")
        written.append(target)
        if f"({target.name})" not in idx:
            idx += line
            lines.append(line)
    if write and lines:
        idx_path.write_text(idx, encoding="utf-8")
    return {"written": written, "skipped": skipped, "index_lines": lines}


def propose(root: Path, p: dict) -> list[tuple[str, str, str]]:
    """Render only. `root` is where a memo WOULD go; nothing here writes under it."""
    return [memo_text(l) for l in p["outbound"]]


def brief(p: dict) -> str:
    a, b = len(p["inbound"]), len(p["outbound"])
    if not a and not b and not p["diverged"] and not p.get("misplaced") and not p.get("unreadable"):
        return "brain: in sync with local memory"
    parts = []
    if a:
        parts.append(f"{a} memo(s) not in local memory (brain-sync local --pull)")
    if b:
        parts.append(f"{b} local lesson(s) not in the brain (brain-sync local --propose)")
    if p["diverged"]:
        parts.append(f"{len(p['diverged'])} diverged")
    if p.get("misplaced"):
        parts.append(f"{len(p['misplaced'])} memo(s) at the brain root (belong under memos/<type>/)")
    if p.get("unreadable"):
        parts.append(f"{len(p['unreadable'])} memo(s) without frontmatter (unreadable)")
    return "brain: " + " · ".join(parts)


def report(root: Path, store: Path, p: dict) -> str:
    out = [f"brain memos: {p['brain']} ({(root / BRAIN).as_posix()}) · local memories: {p['local']} ({store})",
           "excluded: " + ", ".join(f"{t}={n}" for t, n in p["excluded"].items())
           + f"  ({'/'.join(sorted(NEVER_SYNCED))}: never synced; {'/'.join(sorted(LISTED_NOT_PROPOSED))}: listed, not proposed)",
           f"inbound  (brain → local pointers): {len(p['inbound'])}"]
    out += [f"  + {m['name']}  ← {m['path'].relative_to(root).as_posix()}" for m in p["inbound"]]
    out.append(f"outbound (local → brain candidates): {len(p['outbound'])}")
    out += [f"  ? {l['name']}  [{l['type']}]  {l['path'].name}" for l in p["outbound"]]
    out.append(f"diverged (same lesson, different bodies — both sides shown, you adjudicate): {len(p['diverged'])}")
    for m, l in p["diverged"]:
        out.append(f"  ! {m['key']}: repo {m['path'].relative_to(root).as_posix()} vs local {l['path']}")
    if p["misplaced"]:
        out.append(f"misplaced (memos at the brain root; they belong under memos/<type>/): {len(p['misplaced'])}")
        out += [f"  ~ {m['path'].relative_to(root).as_posix()}  →  {m['misplaced'].as_posix()}" for m in p["misplaced"]]
    if p.get("unreadable"):
        out.append(f"unreadable (memo-shaped, no frontmatter `name` — the bridge cannot carry them; add the frontmatter): {len(p['unreadable'])}")
        out += [f"  x {q.relative_to(root).as_posix()}" for q in p["unreadable"]]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--pull", action="store_true")
    mode.add_argument("--propose", action="store_true")
    mode.add_argument("--selftest", action="store_true")
    ap.add_argument("--write", action="store_true", help="with --pull: apply the plan (default prints it)")
    ap.add_argument("--brief", action="store_true", help="with --status: one line, for the SessionStart hook")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", default=".", help="project root (default: cwd)")
    ap.add_argument("--store", help="override the auto-memory directory (default: derived from --root)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    root = Path(a.root)
    store = Path(a.store) if a.store else store_dir(root, Path(os.environ.get("HOME", str(Path.home()))))
    if not (root / BRAIN).is_dir():
        print(f"n/a: no {BRAIN.as_posix()} under {root.resolve()} — /rails-flow:setup-flow scaffolds it")
        return 3
    if not store.is_dir():
        print(f"n/a: no auto-memory store at {store} — this harness keeps none for this path, or the path differs")
        return 3
    try:
        p = plan(brain_memos(root), local_memories(store))
    except (OSError, UnicodeDecodeError) as exc:
        print(f"cannot read the inputs: {exc}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({"brain": p["brain"], "local": p["local"], "excluded": p["excluded"],
                          "inbound": [m["name"] for m in p["inbound"]],
                          "outbound": [l["name"] for l in p["outbound"]],
                          "diverged": [m["key"] for m, _ in p["diverged"]],
                          "misplaced": [m["path"].relative_to(root).as_posix() for m in p["misplaced"]],
                          "unreadable": [q.relative_to(root).as_posix() for q in p["unreadable"]]}, indent=2))
        return 0
    if a.pull:
        r = pull(root, store, p, a.write)
        verb = "wrote" if a.write else "would write"
        for t in r["written"]:
            print(f"{verb} {t}")
        for t in r["skipped"]:
            print(f"kept   {t}  (exists and is not this tool's pointer — see diverged)")
        print(f"{verb} {len(r['index_lines'])} index line(s) in {store / 'MEMORY.md'}"
              + ("" if a.write else "  — re-run with --write to apply"))
        return 0
    if a.propose:
        items = propose(root, p)
        if not items:
            print("nothing to propose: every local feedback/project memory has a brain counterpart")
        for rel, text, line in items:
            print(f"=== {rel}  (proposed; NOT written — /rails-flow:brain writes it)\n{text}--- index line for {BRAIN.as_posix()}/MEMORY.md:\n{line}")
        return 0
    print(brief(p) if a.brief else report(root, store, p))
    return 0


# ----------------------------------------------------------------------------- selftest

def selftest() -> int:
    n, failures = 0, []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}{(' — ' + detail) if detail else ''}")

    def snapshot(d: Path) -> dict:
        return {p.relative_to(d).as_posix(): p.read_bytes() for p in d.rglob("*") if p.is_file()}

    check("the store path follows the harness's slug rule",
          store_dir(Path("/Users/x/proj"), Path("/h")) == Path("/h/.claude/projects/-Users-x-proj/memory"))
    meta, body = parse_frontmatter('---\nname: zsh\ndescription: "quoted: line"\nmetadata:\n  type: feedback\n  x: 1\n---\n\nbody\n')
    check("frontmatter parses a quoted description and one nested level",
          meta == {"name": "zsh", "description": "quoted: line", "metadata": {"type": "feedback", "x": "1"}} and body.strip() == "body", repr(meta))
    check("an escaped quote in a double-quoted description is unescaped, not leaked",
          parse_frontmatter('---\nname: q\ndescription: "it said \\"up to date\\" and lied"\n---\n\nb\n')[0]["description"] == 'it said "up to date" and lied')
    check("a description containing ': ' is quoted in a proposed memo; a plain one is not",
          _yaml_scalar("Rule: do x") == '"Rule: do x"' and _yaml_scalar("Do x, then y") == "Do x, then y"
          and _yaml_scalar('say "hi"') == 'say "hi"' and _yaml_scalar('"quoted" first') == '"\\"quoted\\" first"')
    check("the provenance trailer is not part of the body that divergence compares",
          core_body("Wrap it.\n\n**Why:** x\n\n" + PROVENANCE_PREFIX + " brain-sync; body verbatim, f.md._\n") == "Wrap it.\n\n**Why:** x")
    check("a prefixed brain name and an unprefixed local name are the same lesson",
          key_of("feedback-zsh-word-split") == key_of("zsh-word-split") == "zsh-word-split")

    with tempfile.TemporaryDirectory() as td:
        root, store = Path(td) / "proj", Path(td) / "store"
        (root / BRAIN).mkdir(parents=True); store.mkdir()
        MEMO = "---\nname: feedback-gate-the-commit\ndescription: Gate the commit on the check, not on the print\ntype: feedback\n---\n\nWrap the check in `if`.\n\n**Why:** a FAIL printed and the push ran anyway.\n"
        (root / MEMOS / "feedback").mkdir(parents=True)
        (root / MEMOS / "feedback" / "gate-the-commit.md").write_text(MEMO, encoding="utf-8")
        (root / BRAIN / "STATUS.md").write_text("# Status\n_Updated:_ today\n", encoding="utf-8")
        (root / BRAIN / "MEMORY.md").write_text("- [Gate the commit](memos/feedback/gate-the-commit.md) — gate it\n", encoding="utf-8")
        (store / "zsh-does-not-word-split.md").write_text(
            '---\nname: zsh-does-not-word-split\ndescription: "The Bash tool runs zsh; an unquoted $var is ONE word"\nmetadata:\n  type: feedback\n---\n\nUse `${=var}` or Python.\n', encoding="utf-8")
        (store / "who-i-am.md").write_text('---\nname: who-i-am\ndescription: "the maintainer prefers terse replies"\nmetadata:\n  type: user\n---\n\npersonal\n', encoding="utf-8")
        (store / "dashboard.md").write_text('---\nname: dashboard\ndescription: "the grafana board"\nmetadata:\n  type: reference\n---\n\nhttps://x\n', encoding="utf-8")
        (store / "MEMORY.md").write_text("- [zsh](zsh-does-not-word-split.md) — one word\n", encoding="utf-8")

        brain, local = brain_memos(root), local_memories(store)
        check("STATUS.md and MEMORY.md are not memos", [m["name"] for m in brain] == ["feedback-gate-the-commit"])
        p = plan(brain, local)
        check("a brain memo with no local counterpart is inbound", [m["name"] for m in p["inbound"]] == ["feedback-gate-the-commit"])
        check("a local feedback memory with no brain counterpart is outbound", [l["name"] for l in p["outbound"]] == ["zsh-does-not-word-split"])
        check("a user memory is never synced", not any(l["type"] == "user" for l in p["outbound"]) and p["excluded"]["user"] == 1)
        check("a reference memory is listed, not proposed", not any(l["type"] == "reference" for l in p["outbound"]) and p["excluded"]["reference"] == 1)

        before = snapshot(root) | {f"store/{k}": v for k, v in snapshot(store).items()}
        items = propose(root, p)
        check("propose renders the local body VERBATIM under a brain name",
              len(items) == 1 and items[0][0] == "docs/brain/memos/feedback/zsh-does-not-word-split.md"
              and "Use `${=var}` or Python." in items[0][1] and "name: feedback-zsh-does-not-word-split" in items[0][1], items[0][0] if items else "no items")
        check("propose writes nothing", snapshot(root) | {f"store/{k}": v for k, v in snapshot(store).items()} == before)
        rel, text, _ = items[0]
        (root / rel).write_text(text, encoding="utf-8")            # the human accepts it, as /rails-flow:brain would
        p_acc = plan(brain_memos(root), local_memories(store))
        check("an accepted proposal is neither inbound, outbound nor diverged",
              not any(m["key"] == "zsh-does-not-word-split" for m in p_acc["inbound"]) and not p_acc["outbound"] and p_acc["diverged"] == [],
              f"diverged={[(m['key']) for m, _ in p_acc['diverged']]} outbound={[l['name'] for l in p_acc['outbound']]}")
        (root / rel).unlink()

        dry = pull(root, store, p, write=False)
        check("a dry pull plans one pointer and one index line and writes nothing",
              len(dry["written"]) == 1 and len(dry["index_lines"]) == 1 and snapshot(store) == {k[6:]: v for k, v in before.items() if k.startswith("store/")})
        r = pull(root, store, p, write=True)
        target = store / "feedback-gate-the-commit.md"
        text = target.read_text(encoding="utf-8")
        check("pull writes a pointer memory named after the memo", [t.name for t in r["written"]] == [target.name] and target.is_file())
        check("the pointer carries the memo's own description verbatim",
              "description: Gate the commit on the check, not on the print\n" in text, text)
        check("the pointer's body names the repo file and marks itself",
              "Repo memo: `docs/brain/memos/feedback/gate-the-commit.md`" in text and f"{POINTER_KEY}: true" in text and "type: feedback" in text)
        check("the pointer body is NOT the memo body — a pointer, not a copy", "a FAIL printed" not in text)
        idx = (store / "MEMORY.md").read_text(encoding="utf-8")
        check("MEMORY.md gains exactly one line for it", idx.count("(feedback-gate-the-commit.md)") == 1 and idx.startswith("- [zsh]"))
        after = snapshot(store)
        r2 = pull(root, store, plan(brain_memos(root), local_memories(store)), write=True)
        check("pull is idempotent: a second run writes nothing and the store is byte-identical",
              r2["written"] == [] and r2["index_lines"] == [] and snapshot(store) == after)
        target.unlink()                                   # the file goes, the index line stays
        r3 = pull(root, store, plan(brain_memos(root), local_memories(store)), write=True)
        check("a re-created pointer does not duplicate its index line",
              [t.name for t in r3["written"]] == [target.name] and r3["index_lines"] == []
              and (store / "MEMORY.md").read_text(encoding="utf-8").count("(feedback-gate-the-commit.md)") == 1)
        p2 = plan(brain_memos(root), local_memories(store))
        check("a pointer memory is never proposed outbound", all(l["name"] != "feedback-gate-the-commit" for l in p2["outbound"]))

        # A harness-written file with the same lesson and a different body: never overwritten, reported.
        (root / MEMOS / "feedback" / "zsh-does-not-word-split.md").write_text(
            "---\nname: feedback-zsh-does-not-word-split\ndescription: zsh does not word-split\ntype: feedback\n---\n\nA different body, edited in the repo.\n", encoding="utf-8")
        p3 = plan(brain_memos(root), local_memories(store))
        check("the proposed memo landing in the brain matches the local memory by slug — no duplicate inbound",
              not any(m["key"] == "zsh-does-not-word-split" for m in p3["inbound"]) and not p3["outbound"])
        check("a diverged pair reports both sides", len(p3["diverged"]) == 1 and p3["diverged"][0][0]["path"].name == "zsh-does-not-word-split.md"
              and p3["diverged"][0][1]["path"].name == "zsh-does-not-word-split.md")
        local_bytes = (store / "zsh-does-not-word-split.md").read_bytes()
        pull(root, store, p3, write=True)
        check("pull never overwrites a file it did not write", (store / "zsh-does-not-word-split.md").read_bytes() == local_bytes)
        (root / MEMOS / "feedback" / "raw-note.md").write_text("---\nname: feedback-raw-note\ndescription: a memo\ntype: feedback\n---\n\nbody\n", encoding="utf-8")
        (store / "feedback-raw-note.md").write_text("free text the harness wrote, no frontmatter\n", encoding="utf-8")
        raw_bytes = (store / "feedback-raw-note.md").read_bytes()
        r4 = pull(root, store, plan(brain_memos(root), local_memories(store)), write=True)
        check("a same-named file without frontmatter is kept, not overwritten, and reported",
              (store / "feedback-raw-note.md").read_bytes() == raw_bytes and [t.name for t in r4["skipped"]] == ["feedback-raw-note.md"] and r4["written"] == [])
        # A legacy memo at the brain root: read like any other, and reported with the path it belongs at.
        (root / BRAIN / "feedback_old-style.md").write_text("---\nname: feedback-old-style\ndescription: an old memo\ntype: feedback\n---\n\nold\n", encoding="utf-8")
        p_root = plan(brain_memos(root), local_memories(store))
        check("a memo at the brain root is read and reported misplaced with its memos/<type>/ path",
              any(m["name"] == "feedback-old-style" for m in brain_memos(root))
              and [m["misplaced"].as_posix() for m in p_root["misplaced"]] == ["docs/brain/memos/feedback/old-style.md"]
              and "at the brain root" in brief(p_root))
        (root / BRAIN / "feedback_old-style.md").unlink()
        # A memo-shaped file with no frontmatter is a memo the bridge cannot carry: reported, not skipped.
        (root / BRAIN / "feedback_no-frontmatter.md").write_text("# One branch per defect\n\n`[observed]` — text only.\n", encoding="utf-8")
        p_bad = plan(brain_memos(root), local_memories(store))
        check("a memo-shaped file without frontmatter is reported unreadable, not silently skipped",
              [q.name for q in p_bad["unreadable"]] == ["feedback_no-frontmatter.md"] and "without frontmatter" in brief(p_bad)
              and not any(m["name"] == "feedback_no-frontmatter" for m in brain_memos(root)))
        (root / BRAIN / "feedback_no-frontmatter.md").unlink()
        check("STATUS.md without frontmatter is NOT unreadable — it is not memo-shaped",
              plan(brain_memos(root), local_memories(store))["unreadable"] == [])
        check("brief names both directions", "1 diverged" in brief(p3) and brief(p) .startswith("brain: 1 memo(s) not in local memory"))
        check("brief says in sync when nothing moves", brief({"inbound": [], "outbound": [], "diverged": [], "misplaced": [], "unreadable": []}) == "brain: in sync with local memory")

        # Exit codes through main(): n/a is 3, never a pass.
        check("no brain under the root is n/a (exit 3)", main(["--status", "--root", str(Path(td) / "nowhere"), "--store", str(store)]) == 3)
        check("no auto-memory store is n/a (exit 3)", main(["--status", "--root", str(root), "--store", str(Path(td) / "nostore")]) == 3)
        check("--status exits 0 with both stores", main(["--status", "--root", str(root), "--store", str(store), "--brief"]) == 0)

    for f in failures:
        print(f"FAIL {f}")
    print(f"brain_local_sync selftest: {n} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
