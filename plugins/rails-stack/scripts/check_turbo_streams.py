#!/usr/bin/env python3
"""Turbo Stream subscriptions and broadcast partials: the static half of the access control (#2277).

Run:  python3 check_turbo_streams.py [--project DIR]
      python3 check_turbo_streams.py --selftest

WHY. The signature on a Turbo Stream name protects its integrity, not access: `Turbo::StreamsChannel#subscribed` never checks `current_user`, anyone
holding a valid signed name can subscribe, and the name does not expire (turbo-rails v2.0.23, verified by `doctrine-verifier`; see
rails-stack's `skills/hotwire/references/stream-security.md`). So a stream is only as private as the pages that embed its name, and a broadcast
renders with no request and no viewer. Four findings, all from reading the source and never running it:

  1. `turbo_stream_from` with a LITERAL name (a string without interpolation, or a symbol) is one stream every viewer shares: a public stream by
     construction. It is a finding unless `.rails-flow/public-streams.json` declares the name with a reason.
  2. A declaration with no reason, or for a name no view uses, is itself a finding (a declaration is a decision, and a stale one hides a change).
  3. `turbo_stream_from ... channel: Name`: `app/channels/<name>.rb` must exist and its OWN `subscribed` must OPEN with the guard, in one of two shapes: the
     guard clause `reject unless subscription_allowed?` (also `return reject unless ...`), or turbo-rails' own `if ... && subscription_allowed? ... else reject`
     (it subclasses `ActionCable::Channel::Base`). Defining `subscription_allowed?` is not enough: `Turbo::StreamsChannel#subscribed` never calls it, so a
     subclass that only defines the method is still open; a `super` inside `subscribed` has already streamed; comments are stripped, so the name in a comment
     proves nothing. A strict shape beats chasing every bypass: anything else is a finding. **Ambiguity is refused, not parsed**: a channel file with a second
     definition of `subscribed` (a `def` or a `define_method`), a `=begin` block, or anything after `def subscribed` on its own line (a one-liner, a `;`, a
     heredoc opener) is a finding, because Ruby runs forms this reader would read wrongly (the later definition wins; a guarded `def` inside `=begin/=end` is
     not code; a heredoc can hold the guard line).
  4. A partial that a broadcast renders (the `partial:` of a `broadcast_*` call, or the default partial of `broadcasts_to` / `broadcasts`) must not mention
     `current_user`, `current_*`, `session`, `cookies` or `Current.`: there is no request there, so it raises or renders one viewer's data to everyone.

Declarations: `.rails-flow/public-streams.json` is `{"public": [{"stream": "announcements", "reason": "<at least 20 characters>"}]}`.

WHAT IT IS HONESTLY NOT. It reads names and partials. It cannot tell whether the controller that renders `turbo_stream_from @project` authorized
`@project`; that stays a review judgement. A name built at run time from a variable, a record or an array is not judged, and the default partial of
`broadcasts_to` is located by the model's file name pluralised with a plain `s`, so an irregular plural is reported as "not located", never as clean. A
broadcast partial is read as one file: **a helper it calls, or a partial it renders, is not followed**, so `current_user` hidden one level down is not found.
**The channel check enforces the SHAPE of the guard, not its logic**: `subscription_allowed? || true` in the condition, or a `subscription_allowed?` that just returns
`true`, passes; whether the boolean is right stays a review judgement (pinned by two selftest rows).
Every run prints how many calls, channels and partials it read, so a project with none shows a count of 0 and not a bare pass.

Exit codes: 0 clean, 1 findings, 2 the declaration file cannot be read. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

DECLARATIONS = Path(".rails-flow") / "public-streams.json"
VIEW_SUFFIXES = (".erb", ".haml", ".slim", ".rb")
FORBIDDEN = re.compile(r"\bcurrent_[a-z_]+\b|\bsession\b|\bcookies\b|\bCurrent\.")
STREAM_FROM = re.compile(r"\bturbo_stream_from\b\s*\(?\s*([^\n%]*)")
BROADCAST = re.compile(r"\bbroadcast_(?:replace|update|append|prepend|before|after|remove|action|render)(?:_later)?(?:_to)?\b")
BROADCASTS_TO = re.compile(r"^\s*broadcasts(?:_to)?\b", re.M)
MIN_REASON = 20


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def first_argument(args: str) -> tuple[str, str] | None:
    """`(kind, value)` for the first argument of a `turbo_stream_from` call: `("literal", name)` for a plain string or symbol, `("channel", Name)` for a
    `channel:` option anywhere in the call, else None (a record, variable, array or interpolated string: not judged)."""
    channel = re.search(r"\bchannel:\s*([A-Z][\w:]*)", args)
    positional = [p for p in split_arguments(args) if not re.match(r"^(?:[A-Za-z_]\w*:(?!:)|\*\*)", p)]
    # a literal is a PUBLIC stream only when it is the sole stream argument: `turbo_stream_from "x", current_user` is scoped to a viewer
    literal = re.match(r"""^(?:"([^"#]*)"|'([^']*)'|:([A-Za-z_]\w*))$""", positional[0]) if len(positional) == 1 else None
    if literal:
        return "literal", next(g for g in literal.groups() if g is not None)
    if channel:
        return "channel", channel.group(1)
    return None


def split_arguments(args: str) -> list[str]:
    """The top-level, comma-separated arguments of a call's text (quotes and brackets respected; stops at the call's closing paren). Blanks are dropped."""
    parts: list[str] = []
    current, depth, quote = "", 0, None
    for ch in args:
        if quote:
            current += ch
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
            current += ch
        elif ch in "([{":
            depth += 1
            current += ch
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return [p.strip() for p in parts if p.strip()]


def strip_comments(text: str) -> str:
    """The text with Ruby `#` comments removed (a `#` inside a quoted string is kept), so a comment can never satisfy a check."""
    out = []
    for line in text.splitlines():
        quote, cut = None, len(line)
        for k, ch in enumerate(line):
            if quote:
                quote = None if ch == quote else quote
            elif ch in "\"'":
                quote = ch
            elif ch == "#":
                cut = k
                break
        out.append(line[:cut])
    return "\n".join(out)


GUARD_UNLESS = re.compile(r"^(?:return\s+)?reject(?:\s+and\s+return)?\s+unless\s+subscription_allowed\?(?:\(\))?$")


def subscribed_body(code: str) -> str | None:
    """The body of `def subscribed`, from the line after it to the `end` at the same indent (comments already stripped), or None."""
    m = re.search(r"^([ \t]*)def subscribed\b[^\n]*\n", code, re.M)
    if m is None:
        return None
    rest = code[m.end():]
    end = re.search(rf"^{re.escape(m.group(1))}end\b", rest, re.M)
    return rest[: end.start()] if end else rest


def opens_with_guard(body: str) -> bool:
    """True when the FIRST statement of `subscribed` is the guard, in one of the two shapes turbo-rails' own channel and a guard clause give:

        reject unless subscription_allowed?            (also `return reject unless ...`, `reject and return unless ...`)
        if (stream_name = verified_stream_name_from_params).present? && subscription_allowed?   ...  else  reject  end

    Anything else (a `stream_from` before the check, a `super` first) is not the guard. The boolean logic inside the condition is NOT judged."""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not lines:
        return False
    if GUARD_UNLESS.match(lines[0]):
        return True
    if not lines[0].startswith("if "):
        return False
    condition = [lines[0]]
    for ln in lines[1:]:
        if not condition[-1].endswith(("&&", "||", "(", ",", "\\", "and", "or")):
            break
        condition.append(ln)
    return "subscription_allowed?" in " ".join(condition) and any(re.fullmatch(r"reject(?:\(\))?", ln) for ln in lines)


def channel_problem(text: str, name: str) -> str | None:
    """Why a channel file does not check its subscriptions, or None. Its OWN `subscribed` must OPEN with the guard (`opens_with_guard`): turbo-rails'
    `Turbo::StreamsChannel#subscribed` never calls `subscription_allowed?`, so defining the method in a subclass of it checks nothing, and a `super` inside
    `subscribed` has already streamed. Comments are stripped first, so the name in a comment proves nothing."""
    # AMBIGUITY IS A FINDING, NOT SOMETHING TO PARSE AROUND: Ruby runs forms this reader would pick wrongly (a second `def subscribed` wins, a guarded `def`
    # inside `=begin/=end` is not code, a heredoc can hold the guard line, `define_method(:subscribed)` redefines it), and a strict reader beats parsing Ruby.
    if re.search(r"^=begin\b", text, re.M):
        return f"channel {name}: the file has a `=begin`/`=end` block comment, which this check cannot read around: remove it, or the channel cannot be checked"
    code = strip_comments(text)
    defs = len(re.findall(r"\bdef\s+subscribed\b", code))
    defined = len(re.findall(r"\bdefine_method\s*\(?\s*(?::subscribed\b|[\"']subscribed[\"'])", code))
    if defs + defined > 1:
        return f"channel {name}: `subscribed` is defined more than once (def or define_method), so which one runs cannot be read here: keep exactly one plain `def subscribed`"
    if defined:
        return f"channel {name}: `subscribed` is defined with define_method, which this check does not read: write a plain `def subscribed`"
    if re.search(r"\bdef\s+subscribed\b(?![ \t]*(?:\(\s*\))?[ \t]*$)", code, re.M):
        return f"channel {name}: `def subscribed` has more on its own line (a one-liner, `;`, `=`, or a heredoc opener), which this check cannot read: put the body on the lines below"
    body = subscribed_body(code)
    if body is None:
        return (f"channel {name} has no `subscribed` of its own, so it inherits one that never calls subscription_allowed? "
                f"(Turbo::StreamsChannel#subscribed only verifies the signed name): write the channel on ActionCable::Channel::Base with its own `subscribed`")
    if re.search(r"<\s*Turbo::StreamsChannel\b", code) and re.search(r"\bsuper\b", body):
        return f"channel {name}: `subscribed` calls super, and Turbo::StreamsChannel#subscribed has already streamed before any check can run"
    if not opens_with_guard(body):
        return (f"channel {name}: its `subscribed` must OPEN with the guard (`reject unless subscription_allowed?`, or turbo-rails' `if ... && subscription_allowed? ... "
                f"else reject`); a check after another statement, or only in a comment, does not protect the stream")
    return None


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name.split("::")[-1]).lower()


def load_declarations(project: Path) -> tuple[dict[str, str], list[str]]:
    path = project / DECLARATIONS
    if not path.is_file():
        return {}, []
    try:
        data = json.loads(read(path))
        entries = data["public"]
        assert isinstance(entries, list)
    except (ValueError, KeyError, AssertionError):
        raise ValueError(f'{DECLARATIONS} is not {{"public": [{{"stream": ..., "reason": ...}}]}}')
    names, problems = {}, []
    for entry in entries:
        name, reason = (entry.get("stream"), entry.get("reason")) if isinstance(entry, dict) else (None, None)
        if not isinstance(name, str) or not name:
            problems.append(f"{DECLARATIONS}: an entry has no `stream` name")
        elif not isinstance(reason, str) or len(reason.strip()) < MIN_REASON:
            problems.append(f"{DECLARATIONS}: public stream {name!r} has no reason of at least {MIN_REASON} characters")
        else:
            names[name] = reason
    return names, problems


def view_files(project: Path) -> list[Path]:
    return sorted(p for root in ("app/views", "app/components", "app/helpers") for p in (project / root).rglob("*") if p.is_file() and p.suffix in VIEW_SUFFIXES)


def partial_candidates(project: Path, partial: str) -> list[Path]:
    """`messages/message` -> `app/views/messages/_message.*`."""
    directory, _, name = partial.rpartition("/")
    base = project / "app" / "views" / directory
    return sorted(base.glob(f"_{name.lstrip('_')}.*")) if base.is_dir() else []


def broadcast_partials(project: Path) -> tuple[list[tuple[Path, str]], int]:
    """`([(partial file, where it is reached from)], default partials that could not be located)`."""
    found: list[tuple[Path, str]] = []
    unlocated = 0
    sources = sorted(p for root in ("app/models", "app/jobs", "app/controllers", "app/services", "app/channels") for p in (project / root).rglob("*.rb"))
    for src in sources:
        text = read(src)
        starts = [m.start() for m in BROADCAST.finditer(text)]
        for i, start in enumerate(starts):
            window = text[start: starts[i + 1] if i + 1 < len(starts) else start + 400][:400]
            m = re.search(r"""\bpartial:\s*["']([^"']+)["']""", window)
            if m:
                for p in partial_candidates(project, m.group(1)):
                    found.append((p, f"{src.relative_to(project)}:{line_of(text, start)}"))
        if src.parent.name == "models" and BROADCASTS_TO.search(text):
            singular = src.stem
            default = partial_candidates(project, f"{singular}s/{singular}")
            explicit = re.search(r"""\bpartial:\s*["']([^"']+)["']""", text[BROADCASTS_TO.search(text).start():][:300])
            candidates = partial_candidates(project, explicit.group(1)) if explicit else default
            if candidates:
                found.extend((p, f"{src.relative_to(project)} (broadcasts_to)") for p in candidates)
            else:
                unlocated += 1
    return found, unlocated


def run(project: Path) -> tuple[int, list[str]]:
    try:
        declared, findings = load_declarations(project)
    except ValueError as exc:
        return 2, [str(exc)]
    used: set[str] = set()
    calls = channels = 0
    for path in view_files(project):
        text = read(path)
        for m in STREAM_FROM.finditer(text):
            calls += 1
            arg = first_argument(m.group(1))
            where = f"{path.relative_to(project)}:{line_of(text, m.start())}"
            if arg is None:
                continue
            kind, value = arg
            if kind == "literal":
                used.add(value)
                if value not in declared:
                    findings.append(f"{where}: turbo_stream_from {value!r} is a literal name, one stream every viewer shares (a signed name is not access control): "
                                    f"scope it to a record or a user, or declare it public with a reason in {DECLARATIONS}")
            if re.search(r"\bchannel:\s*[A-Z]", m.group(1)):
                channels += 1
                name = re.search(r"\bchannel:\s*([A-Z][\w:]*)", m.group(1)).group(1)
                channel_file = project / "app" / "channels" / f"{snake(name)}.rb"
                channel_text = read(channel_file) if channel_file.is_file() else None
                if channel_text is None:
                    findings.append(f"{where}: channel {name} has no app/channels/{snake(name)}.rb to check")
                elif (problem := channel_problem(channel_text, name)) is not None:
                    findings.append(f"{where}: {problem}")
    for name in sorted(set(declared) - used):
        findings.append(f"{DECLARATIONS}: public stream {name!r} is declared but no view uses it: delete the declaration")
    partials, unlocated = broadcast_partials(project)
    seen: set[tuple[Path, int]] = set()
    for partial, reached in partials:
        text = read(partial)
        for number, line in enumerate(text.splitlines(), 1):
            if FORBIDDEN.search(line) and (partial, number) not in seen:
                seen.add((partial, number))
                findings.append(f"{partial.relative_to(project)}:{number}: a broadcast partial (reached from {reached}) uses `{FORBIDDEN.search(line).group(0)}`; "
                                f"a broadcast renders with no request, session or viewer: pass data as locals")
    summary = (f"{calls} turbo_stream_from call(s), {channels} custom channel(s), {len({p for p, _ in partials})} broadcast partial(s) read"
               + (f", {unlocated} default partial(s) not located" if unlocated else ""))
    if findings:
        return 1, [*findings, summary, f"{len(findings)} finding(s)"]
    return 0, [f"turbo streams: {summary}, 0 findings"]


def _selftest() -> int:
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    def project(files: dict[str, str]) -> tuple[int, list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, text in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")
            try:
                return run(root)
            except Exception as exc:  # noqa: BLE001  a crash fails ITS row, with the label, instead of ending the selftest before the row is reached
                return -1, [f"raised {exc!r}"]

    view = lambda body: {"app/views/rooms/show.html.erb": body}  # noqa: E731
    code, out = project(view("<%= turbo_stream_from @room %>\n"))
    check("a record-scoped stream is clean, and the run says how many calls it read", code == 0 and "1 turbo_stream_from call(s)" in out[0])
    code, out = project(view('<%= turbo_stream_from [current_user, :notifications] %>\n'))
    check("a per-user array stream is clean", code == 0)
    code, out = project(view('<%= turbo_stream_from "room_#{@room.id}" %>\n'))
    check("an interpolated name is not judged", code == 0)
    code, out = project(view('<%= turbo_stream_from "announcements" %>\n'))
    check("a literal string name is a finding with its file:line", code == 1 and any("rooms/show.html.erb:1" in ln and "'announcements'" in ln for ln in out))
    code, out = project(view("<%= turbo_stream_from :feed %>\n"))
    check("a literal symbol name is a finding", code == 1 and any("'feed'" in ln for ln in out))
    decl = {".rails-flow/public-streams.json": json.dumps({"public": [{"stream": "announcements", "reason": "release notes any visitor may read, signed in or not"}]})}
    code, out = project({**view('<%= turbo_stream_from "announcements" %>\n'), **decl})
    check("a literal name declared public with a reason is clean", code == 0)
    code, out = project({**view("<%= turbo_stream_from @room %>\n"), **decl})
    check("a declaration no view uses is a finding", code == 1 and any("declared but no view uses it" in ln for ln in out))
    code, out = project({**view('<%= turbo_stream_from "announcements" %>\n'),
                         ".rails-flow/public-streams.json": json.dumps({"public": [{"stream": "announcements", "reason": "short"}]})})
    check("a declaration with no real reason is a finding", code == 1 and any("no reason" in ln for ln in out))
    code, out = project({**view('<%= turbo_stream_from "x" %>\n'), ".rails-flow/public-streams.json": "{not json"})
    check("a declaration file that cannot be read is exit 2", code == 2)
    code, out = project(view("<%= turbo_stream_from @room, channel: AuditChannel %>\n"))
    check("a custom channel with no file is a finding", code == 1 and any("no app/channels/audit_channel.rb" in ln for ln in out))
    only_defines = {"app/channels/audit_channel.rb": "class AuditChannel < Turbo::StreamsChannel\n  def subscription_allowed?\n    true\n  end\nend\n"}
    code, out = project({**view("<%= turbo_stream_from @room, channel: AuditChannel %>\n"), **only_defines})
    check("a subclass of Turbo::StreamsChannel that only defines subscription_allowed? is still open: a finding", code == 1 and any("no `subscribed` of its own" in ln for ln in out))
    defined_not_called = {"app/channels/audit_channel.rb": "class AuditChannel < ActionCable::Channel::Base\n  def subscribed\n    stream_from verified_stream_name_from_params\n  end\n\n"
                          "  def subscription_allowed?\n    true\n  end\nend\n"}
    code, out = project({**view("<%= turbo_stream_from @room, channel: AuditChannel %>\n"), **defined_not_called})
    check("a channel whose subscribed never calls subscription_allowed? is a finding", code == 1 and any("must OPEN with the guard" in ln for ln in out))
    good = {"app/channels/audit_channel.rb": "class AuditChannel < ActionCable::Channel::Base\n  extend Turbo::Streams::Broadcasts, Turbo::Streams::StreamName\n"
            "  include Turbo::Streams::StreamName::ClassMethods\n\n  def subscribed\n    if (stream_name = verified_stream_name_from_params).present? && subscription_allowed?\n"
            "      stream_from stream_name\n    else\n      reject\n    end\n  end\n\n  def subscription_allowed?\n    current_user.admin?\n  end\nend\n"}
    code, out = project({**view("<%= turbo_stream_from @room, channel: AuditChannel %>\n"), **good})
    check("the documented custom channel (its own subscribed calls subscription_allowed?) is clean", code == 0)
    def channel(subscribed_body: str, parent: str = "ActionCable::Channel::Base", extra: str = "") -> dict[str, str]:
        return {"app/channels/audit_channel.rb": f"class AuditChannel < {parent}\n  def subscribed\n{subscribed_body}  end\n\n  def subscription_allowed?\n{extra or '    current_user.admin?' + chr(10)}  end\nend\n"}

    page = view("<%= turbo_stream_from @room, channel: AuditChannel %>\n")
    code, out = project({**page, **channel("    # subscription_allowed? goes here\n    stream_from verified_stream_name_from_params\n")})
    check("the name only in a comment is not the guard: a finding", code == 1 and any("must OPEN with the guard" in ln for ln in out))
    code, out = project({**page, **channel("    return stream_from(verified_stream_name_from_params)\n    reject unless subscription_allowed?\n")})
    check("a stream_from before the check (return stream_from(x)) is a finding", code == 1 and any("must OPEN with the guard" in ln for ln in out))
    code, out = project({**page, **channel("    super\n    reject unless subscription_allowed?\n", parent="Turbo::StreamsChannel")})
    check("super inside subscribed on a Turbo::StreamsChannel subclass is a finding (it has already streamed)", code == 1 and any("calls super" in ln for ln in out))
    two_defs = ("class AuditChannel < ActionCable::Channel::Base\n  def subscribed\n    reject unless subscription_allowed?\n    stream_from verified_stream_name_from_params\n  end\n\n"
                "  def subscribed\n    stream_from verified_stream_name_from_params\n  end\n\n  def subscription_allowed?\n    false\n  end\nend\n")
    code, out = project({**page, "app/channels/audit_channel.rb": two_defs})
    check("two `def subscribed`, the unguarded one winning, is a finding", code == 1 and any("defined more than once" in ln for ln in out))
    in_block = ("class AuditChannel < ActionCable::Channel::Base\n=begin\n  def subscribed\n    reject unless subscription_allowed?\n  end\n=end\n"
                "  def subscribed\n    stream_from verified_stream_name_from_params\n  end\n\n  def subscription_allowed?\n    false\n  end\nend\n")
    code, out = project({**page, "app/channels/audit_channel.rb": in_block})
    check("a guarded def inside =begin/=end, then the real one, is a finding", code == 1 and any("=begin" in ln for ln in out))
    heredoc = ("class AuditChannel < ActionCable::Channel::Base\n  def subscribed; stream_from verified_stream_name_from_params; end; X = <<~R\n    reject unless subscription_allowed?\n  R\n\n"
               "  def subscription_allowed?\n    false\n  end\nend\n")
    code, out = project({**page, "app/channels/audit_channel.rb": heredoc})
    check("a one-liner `def subscribed; ...; end` with a heredoc holding the guard line is a finding", code == 1 and any("more on its own line" in ln for ln in out))
    code, out = project({**page, "app/channels/audit_channel.rb": "class AuditChannel < ActionCable::Channel::Base\n  def subscribed()\n    reject unless subscription_allowed?\n    stream_from verified_stream_name_from_params\n  end\n\n  def subscription_allowed?\n    true\n  end\nend\n"})
    check("`def subscribed()` with empty parentheses and the body below is clean", code == 0)
    redefined = ("class AuditChannel < ActionCable::Channel::Base\n  def subscribed\n    reject unless subscription_allowed?\n    stream_from verified_stream_name_from_params\n  end\n\n"
                 "  define_method(:subscribed) { stream_from verified_stream_name_from_params }\n\n  def subscription_allowed?\n    false\n  end\nend\n")
    code, out = project({**page, "app/channels/audit_channel.rb": redefined})
    check("define_method(:subscribed) after a guarded def is a finding", code == 1 and any("defined more than once" in ln for ln in out))
    only_define_method = redefined.replace("  def subscribed\n    reject unless subscription_allowed?\n    stream_from verified_stream_name_from_params\n  end\n\n", "")
    code, out = project({**page, "app/channels/audit_channel.rb": only_define_method})
    check("a channel whose only subscribed is a define_method is a finding (not read)", code == 1 and any("define_method" in ln for ln in out))
    code, out = project({**page, **channel("    reject unless subscription_allowed?\n    stream_from verified_stream_name_from_params\n")})
    check("the guard clause `reject unless subscription_allowed?` is clean", code == 0)
    code, out = project({**page, **channel("    # only a signed-in admin may listen\n    reject unless subscription_allowed? # the guard\n    stream_from verified_stream_name_from_params\n")})
    check("a comment before, or after, the guard does not hide it: clean", code == 0)
    code, out = project({**page, **channel("    return reject unless subscription_allowed?\n    stream_from verified_stream_name_from_params\n")})
    check("`return reject unless subscription_allowed?` is clean", code == 0)
    # STATED LIMITS, pinned: the check enforces the shape of the guard, not the boolean logic inside it
    code, out = project({**page, **channel("    if (stream_name = verified_stream_name_from_params).present? && subscription_allowed? || true\n      stream_from stream_name\n    else\n      reject\n    end\n")})
    check("LIMIT: `subscription_allowed? || true` in the upstream shape passes (the boolean logic is a review judgement)", code == 0)
    code, out = project({**page, **channel("    reject unless subscription_allowed?\n    stream_from verified_stream_name_from_params\n", extra="    true\n")})
    check("LIMIT: a subscription_allowed? that just returns true passes (the boolean logic is a review judgement)", code == 0)
    code, out = project({**view('<%= turbo_stream_from "room", channel: AuditChannel %>\n'), **good})
    check("a literal stream name with a channel that checks the subscription still reads as public (a name is not access)", code == 1 and any("'room'" in ln for ln in out))
    code, out = project(view('<%= turbo_stream_from "x", current_user %>\n'))
    check("a literal beside a viewer streamable is scoped, not public", code == 0)
    code, out = project(view('<%= turbo_stream_from("x", @room) %>\n'))
    check("a literal beside a record, in parentheses, is scoped, not public", code == 0)
    code, out = project(view('<%= turbo_stream_from "x", data: { a: 1 } %>\n'))
    check("a literal with only keyword options is the sole stream argument: public", code == 1)
    model = {"app/models/message.rb": "class Message < ApplicationRecord\n  broadcasts_to :room\nend\n"}
    code, out = project({**model, "app/views/messages/_message.html.erb": "<p><%= current_user.name %></p>\n"})
    check("the default partial of broadcasts_to that uses current_user is a finding", code == 1 and any("_message.html.erb:1" in ln and "current_user" in ln for ln in out))
    code, out = project({**model, "app/views/messages/_message.html.erb": "<p><%= message.body %></p>\n"})
    check("a viewer-neutral broadcast partial is clean", code == 0 and "1 broadcast partial(s)" in out[0])
    code, out = project({"app/views/messages/_message.html.erb": "<p><%= current_user.name %></p>\n"})
    check("the same partial, reached by no broadcast, is not judged", code == 0)
    job = {"app/jobs/notify_job.rb": "class NotifyJob < ApplicationJob\n  def perform(m)\n    Turbo::StreamsChannel.broadcast_append_later_to m.room,\n      partial: \"messages/message\", locals: { message: m }\n  end\nend\n"}
    code, out = project({**job, "app/views/messages/_message.html.erb": "<%= session[:locale] %>\n"})
    check("an explicit partial: of a broadcast call is followed, and session is forbidden", code == 1 and any("session" in ln and "notify_job.rb" in ln for ln in out))
    code, out = project({**job, "app/views/messages/_message.html.erb": "<%= Current.user.name %>\n"})
    check("Current. is forbidden in a broadcast partial", code == 1)
    code, out = project({"app/models/category.rb": "class Category < ApplicationRecord\n  broadcasts\nend\n"})
    check("a default partial that cannot be located is reported, not passed in silence", code == 0 and "1 default partial(s) not located" in out[0])
    code, out = project({"config/application.rb": "module App; end\n"})
    check("a project with none of this reads zero and says so", code == 0 and out[0].startswith("turbo streams: 0 turbo_stream_from call(s), 0 custom channel(s), 0 broadcast partial(s)"))
    print(f"check_turbo_streams selftest: {ok} checks passed, {len(bad)} failed")
    for label in bad:
        print(f"  FAIL: {label}", file=sys.stderr)
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_turbo_streams.py", description=__doc__.splitlines()[0])
    ap.add_argument("--project", type=Path, default=Path.cwd(), help="the Rails project (default: the current directory)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    code, lines = run(args.project.resolve())
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
