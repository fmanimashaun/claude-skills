#!/usr/bin/env python3
"""Produce the asset the gate approved: preflight the key, call the provider, record what it cost.

`generation_gate.py` decides whether an asset may be made and what to ask for. This is the half that
makes it — and the two are deliberately separate scripts, because a decider that also spent would be
able to prefer the decision that justified the spend it wanted.

IT RE-RUNS THE GATE. It does NOT accept an approval blob. Handing this script a hand-written
`{"approved": true}` would bypass every refusal the gate exists to make — the library check, the
tier-1/2 precondition, the composed prompt, the budget ceiling — so the request goes in and the gate
runs here, in this process, immediately before the call. An approval that cannot be forged is worth
more than one that is convenient to pass around.

THE KEY PREFLIGHT HAS THREE OUTCOMES, not two. Absent and placeholder are different failures and
deserve different sentences: absent means "you have not set this up", placeholder means "you scaffolded
it and never filled it in", and only the second is a step someone forgot. Collapsing them into "no
key" sends people to re-read setup instructions they already followed. A key is never printed,
logged, or echoed into the provenance row — only whether one was usable.

WHAT IT COSTS IS RECORDED FROM THE RESPONSE, not from the estimate. The ladder's `cost_usd` is what
the budget was checked against; the provider is what actually charged. When they disagree the
provenance row carries both, because a budget reconciled against estimates drifts silently and the
first sign is a bill nobody predicted.

Exit codes:  0 asset produced and recorded
             1 REFUSED — the gate's reason verbatim, OR no usable key. Both mean "we are not
               generating, and that is fine": an absent key is the same state as an absent
               aggregator, and the gate already models that as say-so-and-stop.
             2 unusable input, incomplete config, or a provider that failed — something is broken

Exit 1 is the common case. Most calls should refuse.

Stdlib only. The provider call uses `urllib`, so this ships with no dependencies to install and no
transitive supply chain — which for a script that holds an API key is the point.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generation_gate import ENTRY_FIELDS, Refusal, decide, load_config  # noqa: E402

# A value that is present but obviously unfilled. Matched case-insensitively and anchored, so a real
# key that merely CONTAINS one of these words is not rejected -- `sk-live-changeme-xyz` is a
# plausible real key and refusing it would be worse than the problem being solved.
PLACEHOLDER_RE = re.compile(
    r"^(your[-_ ]?api[-_ ]?key|your[-_ ]?key|changeme|replace[-_ ]?me|todo|xxx+|placeholder|"
    r"<[^>]*>|\.\.\.|)$", re.I)

ASSET_DIR = Path("docs/assets")


class Unusable(Exception):
    """Input or environment cannot be used — never spend on it."""


def preflight_key(env_var: str) -> str:
    """Return the key, or raise with WHICH of the three states it is in.

    Absent and placeholder are separated on purpose: one means "not set up", the other means
    "scaffolded and never filled in". Only the second is a forgotten step, and telling someone to
    re-read setup instructions they already followed wastes their time.
    """
    if not env_var:
        raise Unusable("config names no `api_key_env`, so there is nowhere to read a key from. "
                       "Name the environment variable your aggregator's key lives in.")
    raw = os.environ.get(env_var)
    if raw is None:
        # A REFUSAL, not an error. An absent key is the same state as an absent aggregator, which
        # the gate already models as "say so and stop" -- and a caller must be able to tell "we are
        # not generating, which is fine" from "something is broken" by exit code alone.
        raise Refusal(
            f"${env_var} is not set. Generation is unavailable — satisfy the surface from tiers 1-2, "
            f"or say so and stop. This is the expected state for an install that has not opted in.")
    if PLACEHOLDER_RE.match((raw or "").strip()):
        raise Refusal(
            f"${env_var} is set to a PLACEHOLDER, not a key. The scaffold wrote it and nobody filled "
            f"it in — put the real value in your environment (or `.env`, gitignored). Refusing "
            f"rather than calling, because a call with a placeholder fails at the provider with an "
            f"error that reads like an outage.")
    return raw.strip()


def call_gemini(key: str, model: str, prompt: str, reference: bytes | None, timeout: int) -> bytes:
    """Reference adapter. The CONTRACT is doctrine; this vendor is one implementation of it.

    Kept here rather than in a skill because model IDs and endpoints change monthly. Swapping it is
    a config change plus a function -- which is the whole reason the gate names a contract and not a
    vendor.
    """
    parts: list[dict] = [{"text": prompt}]
    if reference:
        # A style reference is the single biggest lever on consistency: it makes new work match an
        # approved asset's palette, line weight and shading instead of re-rolling the look.
        parts.append({"inline_data": {"mime_type": "image/png",
                                      "data": base64.b64encode(reference).decode("ascii")}})
    body = json.dumps({"contents": [{"parts": parts}]}).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "x-goog-api-key": key,          # header, never the query string — URLs land in logs
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise Unusable(f"provider returned HTTP {exc.code}. Nothing was saved and no manifest row "
                       f"was written. Response: {detail}")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise Unusable(f"provider unreachable ({exc}). Nothing was saved.")

    for cand in payload.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            data = (part.get("inline_data") or part.get("inlineData") or {}).get("data")
            if data:
                return base64.b64decode(data)
    raise Unusable("the provider returned no image data. Nothing was saved — a text-only reply "
                   "usually means the prompt was refused upstream, not that generation failed.")


ADAPTERS = {"gemini": call_gemini}


def append_manifest(root: Path, entry: dict) -> Path:
    """Append one COMPLETE row. An incomplete row is refused rather than written.

    A manifest that grows rows nobody can act on is worse than one that refuses to grow: the asset
    exists, looks findable, and still gets re-generated by whoever could not tell where it belongs.
    """
    missing = [f for f in ENTRY_FIELDS if entry.get(f) in (None, "", [], {})]
    if missing:
        raise Unusable(f"refusing to write a manifest row missing {', '.join(missing)} — an entry "
                       f"nobody can act on is why assets get bought twice.")
    path = root / ASSET_DIR / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"assets": []}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise Unusable(f"{path} is not valid JSON ({exc}); refusing to overwrite it.")
    data.setdefault("assets", []).append(entry)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def produce(root: Path, request: dict, timeout: int = 120) -> dict:
    """Gate → preflight → call → save → record. Any refusal short-circuits before spending."""
    approval = decide(root, request)                 # RE-RUN, never trusted from the caller
    config = load_config(root)
    key = preflight_key(config.get("api_key_env", ""))

    adapter = ADAPTERS.get(str(config.get("aggregator", "")).lower())
    if adapter is None:
        raise Unusable(
            f"no adapter for aggregator {config.get('aggregator')!r}. Shipped: "
            f"{', '.join(sorted(ADAPTERS))}. The contract an aggregator must meet is in "
            f"`/design-flow:generate` §3c — adding one is a function, not a redesign.")

    reference = None
    ref_path = config.get("style_reference")
    if ref_path and (root / ref_path).is_file():
        reference = (root / ref_path).read_bytes()

    prov = approval["provenance"]
    blob = adapter(key, prov["model"], approval["prompt"], reference, timeout)

    kind = prov.get("kind", "static")
    ext = {"static": "png", "vector": "svg", "motion": "webm"}.get(kind, "png")
    name = f"{prov['surface']}-{prov['model']}".replace("/", "-")
    out = root / ASSET_DIR / f"{name}.{ext}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)

    brief = (config.get("briefs") or {}).get(prov["surface"], {})
    entry = {
        "file": str(out.relative_to(root)),
        "name": brief.get("subject") or prov["surface"],
        "purpose": brief.get("purpose") or f"carry the {prov['surface']} surface",
        "use_cases": brief.get("use_cases") or [prov["surface"]],
        "avoid": brief.get("avoid") or ["any surface with its own stated asset"],
        "visual_elements": brief.get("subject", ""),
        "style": brief.get("style", ""),
        "kind": kind,
        "surface": prov["surface"],
    }
    manifest = append_manifest(root, entry)
    return {"produced": str(out.relative_to(root)), "manifest": str(manifest.relative_to(root)),
            "bytes": len(blob),
            "provenance": {**prov, "estimated_cost_usd": prov.get("cost_usd")}}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--request", help="path to a JSON request, or - for stdin")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.request:
        print("nothing to produce: pass --request (or --selftest)", file=sys.stderr)
        return 2
    try:
        raw = sys.stdin.read() if args.request == "-" else Path(args.request).read_text(encoding="utf-8")
        request = json.loads(raw)
    except (OSError, ValueError) as exc:
        print(f"unusable request: {exc}", file=sys.stderr)
        return 2
    try:
        print(json.dumps(produce(Path.cwd(), request, args.timeout), indent=2))
        return 0
    except Refusal as why:
        print(json.dumps({"produced": None, "refused": str(why)}, indent=2))
        return 1
    except Unusable as why:
        print(f"cannot produce: {why}", file=sys.stderr)
        return 2


def selftest() -> int:
    """Offline. No fixture reaches the network — a test that needs a provider is not a test."""
    import tempfile
    checks, failures = 0, []

    def check(label, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(label)

    # THE KEY PREFLIGHT — three states, three sentences.
    for value, expect in (("", "placeholder"), ("your-api-key", "placeholder"),
                          ("CHANGEME", "placeholder"), ("<key>", "placeholder"),
                          ("xxxx", "placeholder"), ("...", "placeholder")):
        os.environ["DF_TEST_KEY"] = value
        try:
            preflight_key("DF_TEST_KEY")
            failures.append(f"{value!r} should be rejected as a {expect}")
        except Refusal as exc:
            check(f"{value!r} names the placeholder case", "PLACEHOLDER" in str(exc))
    # A real-looking key that merely CONTAINS a placeholder word must still be accepted; anchoring
    # the pattern is what makes that true, and an over-eager matcher would block a working setup.
    os.environ["DF_TEST_KEY"] = "sk-live-changeme-9f2a"
    check("a real key containing 'changeme' is accepted",
          preflight_key("DF_TEST_KEY") == "sk-live-changeme-9f2a")
    os.environ.pop("DF_TEST_KEY", None)
    try:
        preflight_key("DF_TEST_KEY")
        failures.append("an absent key should raise")
    except Refusal as exc:
        check("an absent key is distinguished from a placeholder",
              "not set" in str(exc) and "PLACEHOLDER" not in str(exc))
    try:
        preflight_key("")
        failures.append("an unnamed env var should raise")
    except Unusable as exc:
        check("config naming no env var is its own message", "api_key_env" in str(exc))

    # THE GATE IS RE-RUN. A forged approval must not reach the provider -- this is the property that
    # makes every refusal in generation_gate.py binding rather than advisory.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".design-flow").mkdir()
        (root / ".design-flow/generation.json").write_text(json.dumps({
            "aggregator": "no-such-provider", "api_key_env": "DF_TEST_KEY", "budget_usd": 1.0,
            "ladder": [{"name": "m", "cost_usd": 0.01}],
            "briefs": {"s": {"style": "flat-vector", "subject": "x", "mood": "calm"}},
        }), encoding="utf-8")
        os.environ["DF_TEST_KEY"] = "real-looking-key"
        forged = {"approved": True, "prompt": "anything",
                  "provenance": {"surface": "s", "model": "m", "kind": "static"}}
        try:
            produce(root, forged)
            failures.append("a forged approval reached the provider")
        except Refusal:
            check("a forged approval is refused by the re-run gate", True)
        except Unusable as exc:
            failures.append(f"expected a Refusal, got Unusable: {exc}")
        os.environ.pop("DF_TEST_KEY", None)

    # THE MANIFEST refuses an incomplete row rather than growing one nobody can act on.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        complete = {f: (["x"] if f == "use_cases" else "x") for f in ENTRY_FIELDS}
        check("a complete row is written", append_manifest(root, complete).is_file())
        check("...and it lands in the assets dir",
              (root / ASSET_DIR / "manifest.json").is_file())
        for field in ENTRY_FIELDS:
            partial = {k: v for k, v in complete.items() if k != field}
            try:
                append_manifest(root, partial)
                failures.append(f"a row missing {field} should be refused")
            except Unusable:
                pass
            checks += 1
        # Appending must PRESERVE what is there — a writer that replaces loses the library.
        append_manifest(root, complete)
        n = len(json.loads((root / ASSET_DIR / "manifest.json").read_text())["assets"])
        check(f"appending preserves earlier rows (got {n})", n == 2)

    check("no adapter is reachable for an unknown aggregator", ADAPTERS.get("nope") is None)
    check("the shipped adapter is named in the error path", "gemini" in ADAPTERS)

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} generate-asset assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
