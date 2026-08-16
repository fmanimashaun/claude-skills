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
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompt_library  # noqa: E402
from generation_gate import ENTRY_FIELDS, Refusal, decide, load_config  # noqa: E402

# A value that is present but obviously unfilled. Matched case-insensitively and anchored, so a real
# key that merely CONTAINS one of these words is not rejected -- `sk-live-changeme-xyz` is a
# plausible real key and refusing it would be worse than the problem being solved.
PLACEHOLDER_RE = re.compile(
    r"^(your[-_ ]?api[-_ ]?key|your[-_ ]?key|changeme|replace[-_ ]?me|todo|xxx+|placeholder|"
    r"<[^>]*>|\.\.\.|)$", re.I)

ASSET_DIR = Path("docs/assets")
# #625/#628/#629 — MAINTAINER DECISION, recorded on those issues rather than derived from any
# upstream: the assets dir splits into two named folders, so the finished artefacts and the prompt
# library each have a home instead of everything landing in one flat directory beside the indexes.
#
# The indexes STAY at the assets-dir root -- `plan.json`/`plan.md` and `manifest.json` describe the
# contents, so root holds descriptions and the subfolders hold contents. Leaving `manifest.json`
# where it is also means no existing project has to move a file, and every doc and command that
# already names `docs/assets/manifest.json` keeps working.
#
# Kebab, not the space the layout was drawn with: a path with a space in it breaks every unquoted
# shell one-liner in our own docs, and `lint_markdown_shell.py` checks 191 of those.
ASSET_LIBRARY = ASSET_DIR / "assets-library"


class Unusable(Exception):
    """Input or environment cannot be used — never spend on it."""


def dotenv_value(root: Path, name: str) -> str | None:
    """Read one key from a `.env` file, because two shipped messages promise this works.

    They said *"put the real value in your environment (or a gitignored .env)"* while the code read
    `os.environ` and nothing else -- so following the instruction produced a refusal saying the key
    was not set, which reads like a broken tool rather than an unloaded file. Claims-vs-enforcement,
    in the one message a user sees when they are already stuck.

    Deliberately minimal: `KEY=value`, optional `export`, optional matching quotes, `#` comments,
    blank lines. It is NOT a dotenv implementation -- no interpolation, no multi-line values, no
    `${VAR}` expansion. A fuller parser would be a dependency, and this script holds an API key, so
    "no transitive supply chain" is worth more than covering an exotic syntax.

    The real environment WINS. A shell export is the more deliberate act, and someone debugging a
    key would otherwise be overridden by a stale file they had forgotten about.
    """
    path = root / ".env"
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        if key != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return value
    return None


def preflight_key(env_var: str, root: Path | None = None) -> str:
    """Return the key, or raise with WHICH of the three states it is in.

    Absent and placeholder are separated on purpose: one means "not set up", the other means
    "scaffolded and never filled in". Only the second is a forgotten step, and telling someone to
    re-read setup instructions they already followed wastes their time.
    """
    if not env_var:
        raise Unusable("config names no `api_key_env`, so there is nowhere to read a key from. "
                       "Name the environment variable your aggregator's key lives in.")
    raw = os.environ.get(env_var)
    if raw is None and root is not None:
        raw = dotenv_value(root, env_var)      # promised by the message below; now true
    if raw is None:
        # A REFUSAL, not an error. An absent key is the same state as an absent aggregator, which
        # the gate already models as "say so and stop" -- and a caller must be able to tell "we are
        # not generating, which is fine" from "something is broken" by exit code alone.
        raise Refusal(
            f"${env_var} is not set, and no `.env` beside the project defines it. Generation is unavailable — satisfy the surface from tiers 1-2, "
            f"or say so and stop. This is the expected state for an install that has not opted in.")
    if PLACEHOLDER_RE.match((raw or "").strip()):
        raise Refusal(
            f"${env_var} is set to a PLACEHOLDER, not a key. The scaffold wrote it and nobody filled "
            f"it in — put the real value in your environment (or `.env`, gitignored). Refusing "
            f"rather than calling, because a call with a placeholder fails at the provider with an "
            f"error that reads like an outage.")
    return raw.strip()


def image_size(blob: bytes) -> tuple[int, int] | None:
    """Pixel (width, height) from the header, or None when it cannot be read.

    #640. Stdlib only, header-only -- no decode, no dependency. Returning None rather than guessing
    is the whole contract: a caller that cannot measure must say so, because a fabricated dimension
    would be worse than an absent one. Every branch is a documented header layout:

      PNG   IHDR is always the first chunk; width/height are big-endian uint32 at 16..24.
      GIF   logical screen descriptor, LITTLE-endian uint16 at 6..10.
      JPEG  walk the marker segments to an SOFn; height precedes width, and SOF4/SOF8/SOFC are
            not frame headers despite sitting in the range.
      WebP  three sub-formats, and reading only VP8X would silently miss the common ones.
      SVG   `viewBox` first -- it is the RATIO, which is what an aspect check actually wants.
    """
    if blob[:8] == b"\x89PNG\r\n\x1a\n" and blob[12:16] == b"IHDR":
        return (int.from_bytes(blob[16:20], "big"), int.from_bytes(blob[20:24], "big"))
    if blob[:6] in (b"GIF87a", b"GIF89a"):
        return (int.from_bytes(blob[6:8], "little"), int.from_bytes(blob[8:10], "little"))
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        fourcc = blob[12:16]
        if fourcc == b"VP8 " and blob[23:26] == b"\x9d\x01\x2a":
            return (int.from_bytes(blob[26:28], "little") & 0x3FFF,
                    int.from_bytes(blob[28:30], "little") & 0x3FFF)
        if fourcc == b"VP8L" and blob[20:21] == b"\x2f":
            bits = int.from_bytes(blob[21:25], "little")
            return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        if fourcc == b"VP8X":
            return (int.from_bytes(blob[24:27], "little") + 1,
                    int.from_bytes(blob[27:30], "little") + 1)
        return None
    if blob[:3] == b"\xff\xd8\xff":
        i, n = 2, len(blob)
        while i + 9 < n:
            if blob[i] != 0xFF:
                i += 1
                continue
            marker = blob[i + 1]
            # SOF0-SOF15 carry the frame dimensions; C4 (DHT), C8 (JPG) and CC (DAC) sit inside
            # that numeric range and are NOT frame headers. Reading one gives a plausible, wrong
            # size -- which is the failure mode this whole function exists to avoid.
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                return (int.from_bytes(blob[i + 7:i + 9], "big"),
                        int.from_bytes(blob[i + 5:i + 7], "big"))
            seg = int.from_bytes(blob[i + 2:i + 4], "big")
            if seg < 2:
                return None
            i += 2 + seg
        return None
    head = blob[:2048].lstrip()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        text = head.decode("utf-8", "replace")
        box = re.search(r'viewBox\s*=\s*["\']\s*[-\d.]+[,\s]+[-\d.]+[,\s]+([\d.]+)[,\s]+([\d.]+)',
                        text)
        if box:
            try:
                w, h = float(box.group(1)), float(box.group(2))
                if w > 0 and h > 0:
                    return (round(w), round(h))
            except ValueError:
                return None
        # No viewBox: fall back to width/height, but ONLY when both are unitless or px. `width="8cm"`
        # is a physical size whose pixel ratio depends on the renderer, and treating 8 as pixels
        # would compare a centimetre against a pixel.
        dims = []
        for attr in ("width", "height"):
            m = re.search(rf'\b{attr}\s*=\s*["\']([\d.]+)(px)?["\']', text)
            if not m:
                return None
            dims.append(float(m.group(1)))
        return (round(dims[0]), round(dims[1])) if all(d > 0 for d in dims) else None
    return None


# How far a returned image may sit from the aspect that was asked for. STATED, not implied, because
# an unstated tolerance is a threshold nobody can argue with. 2% accepts a 1024x576 for 16:9 exactly
# and a 1024x580 (0.7% off), and refuses a square delivered for a wide band -- which is the failure
# this exists to catch, and it misses by 78%, not by 2%.
ASPECT_TOLERANCE = 0.02


def parse_aspect(text: str | None) -> float | None:
    """`"16:9"` -> 1.777…. None when absent or unparseable, never a guess."""
    if not text:
        return None
    m = re.fullmatch(r"\s*([\d.]+)\s*[:x/]\s*([\d.]+)\s*", str(text))
    if not m:
        return None
    try:
        w, h = float(m.group(1)), float(m.group(2))
    except ValueError:
        return None
    return w / h if w > 0 and h > 0 else None


def assert_aspect(blob: bytes, aspect: str | None) -> None:
    """The bytes must be the shape that was ASKED for. Silent when nothing was asked.

    #640. The flow priced the plan to the cent and then never said whether it wanted a 21:9 band or
    a square card -- and accepted whatever arrived. A square returned for a wide band was recorded
    `done`, entered the manifest, and was found by a human looking at the page.

    UNREADABLE DIMENSIONS PASS. `image_size` returns None for a format it cannot parse, and refusing
    on that would turn "we could not measure" into "the provider was wrong" -- blocking a correct
    asset over our own gap. The honest failure here is a miss, not a false accusation.
    """
    want = parse_aspect(aspect)
    if want is None:
        return
    size = image_size(blob)
    if size is None:
        return
    w, h = size
    if h <= 0:
        return
    got = w / h
    if abs(got - want) / want > ASPECT_TOLERANCE:
        raise Unusable(
            f"the asset is {w}x{h} ({got:.3f}), but the brief asked for {aspect} ({want:.3f}) — "
            f"off by {abs(got - want) / want * 100:.0f}%, and the tolerance is "
            f"{ASPECT_TOLERANCE * 100:.0f}%. Nothing was recorded. A shape that does not fit its "
            f"band gets cropped at composition time, which throws away the part of the picture you "
            f"paid for. Re-run stating the aspect in the prompt, or change the brief if the band "
            f"changed.")


def reference_mime(blob: bytes) -> str:
    """The MIME type of a style-reference image, SNIFFED rather than assumed.

    Every adapter hardcoded `image/png`, which is a lie the moment a project points
    `style_reference` at the `.jpg` it exported from its brand deck -- and a provider that validates
    the declared type against the bytes rejects the call, so the reference is lost at exactly the
    moment it was supposed to be doing the most work. Derived from `sniff_extension` so there is one
    format-detector in this file rather than two that can disagree.
    """
    ext = sniff_extension(blob)
    return {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp",
            "svg": "image/svg+xml"}.get(ext, "image/png")


def call_gemini(key: str, model: str, prompt: str, reference: bytes | None,
                timeout: int) -> tuple[bytes, float | None]:
    """Reference adapter. The CONTRACT is doctrine; this vendor is one implementation of it.

    Kept here rather than in a skill because model IDs and endpoints change monthly. Swapping it is
    a config change plus a function -- which is the whole reason the gate names a contract and not a
    vendor.
    """
    parts: list[dict] = [{"text": prompt}]
    if reference:
        # A style reference is the single biggest lever on consistency: it makes new work match an
        # approved asset's palette, line weight and shading instead of re-rolling the look.
        parts.append({"inline_data": {"mime_type": reference_mime(reference),
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
                # No per-request cost in this response shape, so the provenance keeps the ESTIMATE
                # and says so. Reporting an estimate as if it were the charge is how a budget
                # reconciles cleanly against a bill nobody predicted.
                return base64.b64decode(data), None
    raise Unusable("the provider returned no image data. Nothing was saved — a text-only reply "
                   "usually means the prompt was refused upstream, not that generation failed.")


def call_openrouter(key: str, model: str, prompt: str, reference: bytes | None,
                    timeout: int) -> tuple[bytes, float | None]:
    """OpenRouter — an aggregator, which is what the `aggregator` config field actually wants.

    Preferred over a single vendor for this path because it satisfies all three of the §3e contract
    requirements natively, and the third is the one that matters most here: the response carries
    `usage.cost`, the REAL charge for that request. Everything else in this pipeline budgets against
    an estimate, and an estimate that is never reconciled is how a ceiling drifts until the bill
    arrives. With a real number the provenance row records what was actually spent.

    Verified against https://openrouter.ai/docs/guides/overview/multimodal/image-generation
    (2026-08-08): POST /api/v1/images, bearer auth, `data[].b64_json`, `input_references` for style.
    """
    body: dict = {"model": model, "prompt": prompt}
    if reference:
        # A style reference is the single biggest lever on consistency. Base64 data URL, so no
        # asset has to be publicly hosted before it can be used as a reference.
        body["input_references"] = [{
            "type": "image_url",
            "image_url": {"url": f"data:{reference_mime(reference)};base64,"
                                 + base64.b64encode(reference).decode("ascii")},
        }]
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/images",
        data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})    # header, never the query string
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise Unusable(f"provider returned HTTP {exc.code}. Nothing was saved and no manifest row "
                       f"was written. Response: {detail}")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise Unusable(f"provider unreachable ({exc}). Nothing was saved.")

    cost = (payload.get("usage") or {}).get("cost")
    for item in payload.get("data", []):
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"]), (float(cost) if cost is not None else None)
    raise Unusable("the provider returned no image data. Nothing was saved — a text-only reply "
                   "usually means the prompt was refused upstream, not that generation failed.")


def call_openrouter_svg(key: str, model: str, prompt: str, reference: bytes | None,
                        timeout: int) -> tuple[bytes, float | None]:
    """Ask a TEXT model for raw SVG, which `visual-assets.md` already prefers for vector work.

    An SVG scales, diffs in review, and recolours from tokens without being regenerated -- so for
    icons and flat shapes it beats a raster even when both are available. It is also the only path
    on this provider with a genuinely free tier: image endpoints have no `:free` variant, text ones
    do, so the whole pipeline is testable end to end at zero cost.

    The reference image is IGNORED here rather than silently dropped in the response: a text model
    takes no style reference, and pretending otherwise would make consistency look guaranteed when
    it is not. Consistency for this path comes from the composed prompt alone.
    """
    system = ("You output a single valid SVG document and nothing else. No markdown fence, no "
              "commentary. Start with <svg and end with </svg>. Use a viewBox, no external fonts, "
              "no embedded raster images, and currentColor or the given palette only.")
    body = {"model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise Unusable(f"provider returned HTTP {exc.code}. Nothing was saved and no manifest row "
                       f"was written. Response: {detail}")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise Unusable(f"provider unreachable ({exc}). Nothing was saved.")

    text = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    # A model told "no fence" still sometimes fences. Recovering is right; PRETENDING the output was
    # clean is not, so anything without an <svg> element fails rather than being written as `.bin`.
    start, end = text.find("<svg"), text.rfind("</svg>")
    if start == -1 or end == -1:
        raise Unusable("the model returned no SVG element. Nothing was saved — a text-only reply "
                       "usually means the prompt was refused or the model ignored the format "
                       "instruction, neither of which is an asset.")
    cost = (payload.get("usage") or {}).get("cost")
    return text[start:end + 6].encode("utf-8"), (float(cost) if cost is not None else None)


def call_openrouter_chat_image(key: str, model: str, prompt: str, reference: bytes | None,
                               timeout: int) -> tuple[bytes, float | None]:
    """Raster via `chat/completions` with `modalities: ["image", "text"]`.

    #629. This is a SECOND raster shape on the same provider, not a replacement for `call_openrouter`
    -- and it exists because the current top image models serve this one and not `/api/v1/images`.
    Verified against OpenRouter's chat-completion API reference before writing: `modalities` is a
    request field whose enum is text/image/audio, and the assistant message carries an `images` array
    of `{type, image_url: {url}}`. The reporter's live run added what a reference cannot: the URL is a
    base64 data URL, and `usage.cost` comes back in the same response.

    IT MATTERS THAT THE SCRIPT MAKES THIS CALL. The agent-in-the-loop path dead-ends on a provider
    that answers with an inline image (#628): the agent sees a rendered picture and cannot transcribe
    its bytes. Here the bytes never pass through a model's hands -- they are decoded and written by
    this function -- so a billed generation always produces a file.
    """
    # THE STYLE REFERENCE IS SENT, and the first version of this adapter dropped it. `generate.md`
    # §3e calls a reference image "the single biggest lever on consistency" -- give the provider one
    # approved asset and new work matches its palette, line weight and shading instead of re-rolling
    # the look. This function accepted `reference` and never used it, so a project that had done the
    # work of approving a reference got none of its benefit and no warning either. `call_gemini` and
    # `call_openrouter` both send theirs; `call_openrouter_svg` documents WHY it cannot. Silently
    # dropping it was the one option its own docstring rules out: it makes consistency "look
    # guaranteed when it is not".
    #
    # Multimodal content is a LIST of parts, which is the same `{type, image_url: {url}}` shape
    # OpenRouter's chat-completion reference documents for image input.
    content: list[dict] | str = prompt
    if reference:
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": f"data:{reference_mime(reference)};base64,"
                                  + base64.b64encode(reference).decode("ascii")}},
        ]
    body = {"model": model,
            "modalities": ["image", "text"],
            "messages": [{"role": "user", "content": content}]}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise Unusable(f"provider returned HTTP {exc.code}. Nothing was saved and no manifest row "
                       f"was written. Response: {detail}")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise Unusable(f"provider unreachable ({exc}). Nothing was saved.")

    message = ((payload.get("choices") or [{}])[0].get("message") or {})
    images = message.get("images") or []
    if not images:
        # A TEXT-ONLY REPLY IS NOT AN ASSET, and it is the likeliest failure here: a model that does
        # not support the image modality answers in prose about the picture it would have drawn.
        # Saving that as `.bin` would put a paragraph in the manifest where art belongs.
        text = (message.get("content") or "")[:200]
        raise Unusable(
            f"the model returned no image. `modalities: [image, text]` was requested, so a "
            f"text-only reply means this model does not generate images — check the rung's model ID "
            f"against `--discover`. It said: {text!r}")
    # Indexed through a default: with the guard above removed, `images[0]` raises IndexError
    # and the run dies before any refusal is reported -- and a crash is not a verdict. The
    # mutation guard for that guard found it.
    first = images[0] if images else {}
    url = ((first.get("image_url") or {}).get("url") or "")
    if not url.startswith("data:"):
        raise Unusable(f"the image came back as {url[:60]!r}, which is not a base64 data URL. This "
                       f"adapter decodes `data:` only; if the provider now returns a link, fetch it "
                       f"with `--from-url` rather than guessing here.")
    try:
        blob = base64.b64decode(url.split(",", 1)[1])
    except (ValueError, IndexError) as exc:
        raise Unusable(f"the image data URL did not decode ({exc}). Nothing was saved.")
    if not blob:
        raise Unusable("the image data URL decoded to nothing. Nothing was saved — a 0-byte file in "
                       "the manifest is a `done` row nobody can see.")
    cost = (payload.get("usage") or {}).get("cost")
    return blob, (float(cost) if cost is not None else None)


def call_openrouter_video(key: str, model: str, prompt: str, reference: bytes | None,
                          timeout: int) -> tuple[bytes, float | None]:
    """Motion via the VIDEO endpoint, which is asynchronous: submit, poll, then download.

    This exists because doctrine previously said motion had no route, which was wrong. The claim
    started as a true statement about the IMAGE endpoint -- it returns no video -- and was allowed
    to stand as "there is no route at all", so the scaffold shipped an empty motion ladder and the
    plan refused every motion row. A true sentence about one endpoint became a false one about the
    provider, and nothing checked it because it read like a limitation rather than a claim.

    Three shapes differ from the image path and each is load-bearing:

      * SUBMIT RETURNS 202, not the asset. The response carries a `polling_url` and nothing usable,
        so a caller that treated 2xx as success would save an empty file.
      * POLLING HAS NO CEILING OF ITS OWN. `timeout` is spent across the whole wait here rather than
        per request, because a per-request timeout on a job that takes minutes never fires and the
        run hangs instead of failing.
      * THE URL NEEDS THE SAME AUTH. `unsigned_urls` are OpenRouter paths, not public links; an
        unauthenticated fetch returns an error page that is bytes, and bytes get written to disk.
    """
    body: dict = {"model": model, "prompt": prompt}
    if reference:
        # Style guidance, matching the image path's contract. `frame_images` (first/last frame) is
        # the other mode the API offers and is a different intent -- not a style reference.
        body["input_references"] = [{
            "type": "image_url",
            "image_url": {"url": f"data:{reference_mime(reference)};base64,"
                                 + base64.b64encode(reference).decode("ascii")},
        }]
    auth = {"Authorization": f"Bearer {key}"}

    def _json(req, secs):
        try:
            with urllib.request.urlopen(req, timeout=secs) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            raise Unusable(f"provider returned HTTP {exc.code}. Nothing was saved and no manifest "
                           f"row was written. Response: {detail}")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise Unusable(f"provider unreachable ({exc}). Nothing was saved.")

    job = _json(urllib.request.Request(
        "https://openrouter.ai/api/v1/videos", data=json.dumps(body).encode("utf-8"),
        method="POST", headers={**auth, "Content-Type": "application/json"}), 60)
    poll_url = job.get("polling_url") or f"https://openrouter.ai/api/v1/videos/{job.get('id')}"

    deadline = time.monotonic() + timeout
    state = job
    while state.get("status") in ("pending", "in_progress", None):
        if time.monotonic() > deadline:
            raise Unusable(
                f"the video job did not finish within {timeout}s (last status "
                f"{state.get('status')!r}). Nothing was saved. The job may still complete at "
                f"{poll_url} — raise --timeout rather than assuming it failed.")
        time.sleep(min(15, max(1, deadline - time.monotonic())))
        state = _json(urllib.request.Request(poll_url, headers=auth), 60)

    if state.get("status") != "completed":
        raise Unusable(f"the video job ended {state.get('status')!r}. Nothing was saved. "
                       f"{str(state.get('error') or '')[:200]}")
    urls = state.get("unsigned_urls") or []
    if not urls:
        raise Unusable("the job completed with no video URL. Nothing was saved — a completion "
                       "carrying nothing to download is a provider-side failure, not an asset.")
    try:
        with urllib.request.urlopen(urllib.request.Request(urls[0], headers=auth),
                                    timeout=120) as resp:
            blob = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise Unusable(f"the video URL could not be fetched ({exc}). Nothing was saved.")
    cost = (state.get("usage") or {}).get("cost")
    return blob, (float(cost) if cost is not None else None)


class AgentWrites(Exception):
    """Not a failure — the gate approved, and the AGENT is the generator for this kind.

    Claude Code writes SVG directly, so routing a vector asset through an external model pays for
    a worse result: the agent has the brand pack, the token names and the surrounding components in
    context, and a remote model has a sentence. The discipline still applies in full -- library
    check, tier refusal, composed prompt, budget, provenance -- because the point of the gate was
    never the HTTP call. Only the call is skipped.
    """

    def __init__(self, prompt: str, target: Path, entry: dict):
        self.prompt, self.target, self.entry = prompt, target, entry
        super().__init__("agent-authored")


def call_agent(key, model, prompt, reference, timeout):      # noqa: ARG001 - signature parity
    raise AgentWrites(prompt, Path(), {})


def call_pen(key, model, prompt, reference, timeout):        # noqa: ARG001 - signature parity
    """Compose in pen.dev and export a raster (#599). A LOCAL tool, so there is no key and no HTTP.

    WHY A DESIGN TOOL FOR THIS KIND AT ALL. A composed surface -- an OG card, a social preview, an
    app-store shot -- is layout plus real type at a fixed size. A diffusion model is the wrong
    instrument twice over: it cannot render accurate text, and it cannot render the same brand
    twice. pen composes deterministically and exports PNG, which is exactly that job.

    THE PROMPT IS STILL THE COMPOSED ONE. It arrives from the gate, which refuses a free-typed
    prompt -- so pen's own agent is constrained by the surface class, the aesthetic brief and the
    pack, rather than improvising palette and typography. The vendor's guidance says not to expand a
    user's request with invented creative direction, and this does not: it passes CONSTRAINTS, which
    narrow that agent instead of competing with it.

    A PATH MISS PROVES ONLY THAT THE CLI IS NOT ON PATH. pen.dev also ships as a user-scoped MCP
    server registered outside any repo, so a fully-provisioned machine fails this probe -- measured,
    on a machine where `claude mcp list` reported pencil connected while `which pen` found nothing.
    Saying "pen.dev is not installed" there would send someone to install what they already have.
    """
    import shutil
    import subprocess
    import tempfile

    exe = shutil.which("pen")
    if not exe:
        raise Unusable(
            "the `pen` CLI is not on PATH. That is all a PATH miss proves: pen.dev also ships as a "
            "local MCP server registered outside the repo, so this machine may well have pen.dev "
            "without having this binary. Install the CLI with `npm install -g @pen.dev/cli` if you "
            "want the unattended path, or drop this rung and compose interactively instead. "
            "Nothing was spent.")
    with tempfile.TemporaryDirectory() as td:
        doc, img = Path(td) / "composed.pen", Path(td) / "composed.png"
        cmd = [exe, "--out", str(doc), "--prompt", prompt,
               "--export", str(img), "--export-type", "png", "--export-scale", "2"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            raise Unusable(f"the `pen` CLI could not be run ({exc}). Nothing was saved.")
        if proc.returncode != 0:
            # The CLI's own stderr, verbatim. Paraphrasing a tool's refusal into "generation failed"
            # is how a fixable auth or model problem reads like an outage.
            raise Unusable(f"`pen` exited {proc.returncode}: "
                           f"{(proc.stderr or proc.stdout or '').strip()[:400]}")
        if not img.is_file():
            raise Unusable(
                "`pen` reported success and wrote no image. Exit 0 with no artefact is not a "
                "completion — nothing was recorded.")
        try:
            blob = img.read_bytes()
        except OSError as exc:
            # Belt and braces, and not idle: without it, disabling the check above turns this into
            # a FileNotFoundError traceback rather than a refusal -- and a crash is not a verdict,
            # so the mutation guard on that check could not tell which fixture caught it.
            raise Unusable(f"`pen` wrote an image that could not be read ({exc}).")
    # Cost is NOT reported: the CLI drives its own agent on the operator's Claude auth, so what it
    # spends is Opus-minutes rather than a figure this path can read. Returning None says "unknown"
    # instead of asserting zero, and the ladder's own `cost_usd` is what the budget compares.
    return blob, None


# Adapters that make no authenticated HTTP call of their own, so `api_key_env` is meaningless to
# them. Stated as data because the alternative -- an `if name == "agent"` that a second keyless
# adapter has to remember to join -- is how the agent rung came to demand a key it never used.
KEYLESS = frozenset({"agent", "pen"})

ADAPTERS = {"agent": call_agent,
            "pen": call_pen,
            "openrouter-video": call_openrouter_video,
            "openrouter": call_openrouter,
            # #629. The chat-completions raster shape, which the current top image models serve and
            # `/api/v1/images` does not. Registered as its own name rather than replacing
            # `openrouter`, because both endpoints are live and a project pinned to a model on the
            # images endpoint must not be silently rerouted.
            "openrouter-chat-image": call_openrouter_chat_image,
            "openrouter-svg": call_openrouter_svg,
            "gemini": call_gemini}


# Magic bytes, in the order that distinguishes them. Sniffing beats trusting the request: the caller
# says what it WANTED, the provider decides what it SENT, and only the second determines whether the
# file is usable. Kept to the formats this path can actually produce -- guessing at more would be a
# list nobody maintains.
def sniff_extension(blob: bytes) -> str:
    head = blob[:512].lstrip()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return "svg"
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if blob[:3] == b"\xff\xd8\xff":
        return "jpg"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "webp"
    if blob[4:8] == b"ftyp":
        return "mp4"
    if blob[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    # Lottie is JSON. Sniffed last among the text formats so an SVG is never mistaken for it.
    if head[:1] in (b"{", b"["):
        return "json"
    return "bin"      # unknown, and named honestly rather than guessed at


def assert_kind_matches(kind: str, blob: bytes) -> str:
    """The bytes must be what the kind promised. Returns the sniffed extension.

    Shared by the bought path and the agent path deliberately: an agent-authored asset must get NO
    easier route into the manifest than a purchased one, or "the agent wrote it" becomes the way
    past every refusal. It also exists as a FUNCTION because the check first lived inline in the
    `--record` branch, where the selftest could not reach it -- a mutation removing it survived, and
    the fixture that claimed to cover it was testing `sniff_extension` instead.
    """
    ext = sniff_extension(blob)
    if kind == "motion" and ext not in ("svg", "json"):
        raise Unusable(
            f"kind is `motion` but the bytes are {ext.upper()}. Product motion is Lottie JSON or an "
            f"animated SVG -- a few KB that recolour from tokens and diff in review. A video file "
            f"here is footage: megabytes, fixed palette, un-recolourable. If you meant footage, "
            f"plan the surface as `video`.")
    # THE `video` KIND HAD NO CHECK AT ALL, which was survivable while every video arrived from the
    # async video adapter and is not now: `--from-url` (#628) lets any URL feed any row, so a
    # provider that answered a video request with a still frame -- or a poster image served at the
    # video's URL -- would record a PNG as footage. It opens, it looks plausible in a listing, and
    # the surface plays nothing.
    if kind == "video" and ext not in ("mp4", "webm"):
        raise Unusable(
            f"kind is `video` but the bytes are {ext.upper()}. Footage is MP4 or WebM; a still "
            f"recorded as video renders a frozen frame where motion was planned. Providers do "
            f"serve a poster image at a video's URL, so check you fetched the asset rather than "
            f"its thumbnail — and if you meant a still, plan the surface as `static`.")
    # #641. THE `motion` KIND CHECKED ONLY THE EXTENSION, which both the animated and the static
    # case share -- so a completely static SVG was accepted as a motion asset, the row went `done`,
    # and the surface animated nothing. `.json` was worse: any JSON at all passed as "Lottie".
    # Every other kind asserts something about the bytes; this one asserted a file type.
    if kind == "motion":
        if ext == "svg":
            text = blob.decode("utf-8", "replace")
            # SMIL elements, or a stylesheet carrying an animation. A `<style>` block with
            # `@keyframes` is how a token-recoloured animated SVG is normally authored, so checking
            # only for SMIL would refuse the idiom our own doctrine points at.
            if not re.search(r"<(animate|animateTransform|animateMotion|set)\b", text) \
                    and "@keyframes" not in text and not re.search(r"\banimation\s*:", text):
                raise Unusable(
                    "kind is `motion` but this SVG contains no animation — no `<animate>`, "
                    "`<animateTransform>`, `<animateMotion>` or `<set>`, and no `@keyframes` or "
                    "`animation:` in a `<style>` block. A static drawing recorded as motion is a "
                    "`done` row whose surface animates nothing. Author the movement, or plan the "
                    "surface as `vector`.")
        elif ext == "json":
            try:
                doc = json.loads(blob.decode("utf-8", "replace"))
            except ValueError as exc:
                raise Unusable(f"kind is `motion` and the bytes are JSON, but it does not parse "
                               f"({exc}). Nothing was recorded.")
            # Lottie's required top-level keys: `v` version, `fr` frame rate, `op` out point,
            # `layers`. Checking the SHAPE rather than merely "is JSON" is the whole point -- any
            # JSON at all used to pass as an animation.
            missing = [k for k in ("v", "fr", "op", "layers") if k not in doc]
            if missing:
                raise Unusable(
                    f"kind is `motion` and the bytes are JSON, but this is not a Lottie animation — "
                    f"missing {', '.join(missing)}. A Lottie carries `v` (version), `fr` (frame "
                    f"rate), `op` (out point) and `layers`. Any other JSON recorded here is a "
                    f"`done` row that renders nothing.")
    if kind == "vector" and ext != "svg":
        raise Unusable(
            f"kind is `vector` but the bytes are {ext.upper()}. A raster named `.svg` does not "
            f"scale and cannot be recoloured from tokens, which is why the vector kind exists. "
            f"Point this surface's ladder at an SVG-capable model, let the agent author it, or "
            f"plan the surface as `static`.")
    return ext


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
    approval = decide(root, request)  # produce(): RE-RUN, never trusted from the caller
    config = load_config(root)
    # ADAPTER FIRST, then the key. Ordering it the other way demanded an API key from the one path
    # that never calls an API -- the agent authors the asset itself -- so a zero-cost route refused
    # for a credential it had no use for.
    prov = approval["provenance"]
    # THE RUNG CHOOSES THE ADAPTER, falling back to the global aggregator. Per-kind
    # ladders imply per-rung adapters: a `vector` ladder whose rung is `agent` must not
    # be routed through the project's image aggregator, which is what happened -- the
    # agent rung asked for an API key it would never use, because only the global
    # setting was ever consulted.
    rung = str(prov.get("model", "")).lower()
    name = rung if rung in ADAPTERS else str(config.get("aggregator", "")).lower()
    adapter = ADAPTERS.get(name)
    if adapter is None:
        raise Unusable(
            f"no adapter for aggregator {config.get('aggregator')!r}. Shipped: "
            f"{', '.join(sorted(ADAPTERS))}. The contract an aggregator must meet is in "
            f"`/design-flow:generate` §3e — adding one is a function, not a redesign.")

    # KEYLESS ADAPTERS, named rather than special-cased one at a time. `agent` authors in-process
    # and `pen` shells out to a local CLI that carries its own auth -- neither makes an HTTP call
    # this config could authenticate. Demanding a key here is the exact defect the comment above
    # records for the agent rung: a zero-cost route refused for a credential it has no use for.
    key = "" if name in KEYLESS else preflight_key(config.get("api_key_env", ""), root)

    reference = None
    ref_path = config.get("style_reference")
    if ref_path and (root / ref_path).is_file():
        reference = (root / ref_path).read_bytes()


    try:
        blob, actual_cost = adapter(key, prov["model"], approval["prompt"], reference, timeout)
    except AgentWrites:
        # The gate has ALREADY approved: library searched, tiers refused, prompt composed, budget
        # checked. What is left is authorship, and the agent does that better here than a remote
        # model would. It writes the file, then `--record` validates and registers it -- so nothing
        # reaches the manifest without passing the same checks a bought asset does.
        target = agent_target(root, prov)
        raise AgentWrites(approval["prompt"], target, manifest_entry(root, config, prov, target))

    kind = prov.get("kind", "static")
    # EXTENSION FROM THE BYTES, not from the request. Deriving it from `kind` wrote PNG bytes to a
    # `.svg` and a still frame to a `.webm` -- files that open, look plausible in a listing, and
    # are the wrong format. A raster named `.svg` does not scale and does not recolour from tokens,
    # which is the entire reason a vector asset was asked for.
    ext = assert_kind_matches(kind, blob)
    # #640. The shape too, against what the brief ASKED for — carried on the provenance so this
    # never re-reads config and risks a different answer than the prompt was composed from.
    assert_aspect(blob, prov.get("aspect"))
    # Only [A-Za-z0-9._-] survives. Model IDs carry `/` and `:` (`cohere/x:free`), both legal on
    # this filesystem and hostile on Windows and in URLs -- and an asset path ends up in both.
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{prov['surface']}-{prov['model']}").strip("-")
    out = root / ASSET_LIBRARY / f"{name}.{ext}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)

    entry = manifest_entry(root, config, prov, out)
    manifest = append_manifest(root, entry)
    # THE PROMPT OUTLIVES THE RUN. Money moved here, and until this existed the one artefact that
    # makes the spend repeatable -- the composed prompt -- was printed to stdout and lost with the
    # scrolled buffer.
    warning = remember_prompt(root, config, prov, approval["prompt"],
                              asset=_project_relative(out, root), model=None,
                              actual_cost_usd=actual_cost)
    result = {"produced": str(out.relative_to(root)), "manifest": str(manifest.relative_to(root)),
              "prompts": str((root / prompt_library.LIBRARY_PATH).relative_to(root)),
              "bytes": len(blob),
              "provenance": {**prov,
                             "estimated_cost_usd": prov.get("cost_usd"),
                             "actual_cost_usd": actual_cost}}
    if warning:
        result["prompt_library_warning"] = warning
    return result


VERDICTS = ("accept", "reject")


def critique_brief(root: Path, request: dict, asset: Path) -> dict:
    """What a critic needs to judge an asset, assembled from what the gate already knows.

    THE MISSING STAGE. `acceptance` existed as a string that had to be PRESENT before the ladder
    could climb -- which satisfied the acceptance criterion in letter and not in spirit: nothing
    ever read the asset, so "climb because the output was not good enough" had a trigger nobody
    could pull. `attempt` existed and nothing ever set it.

    It is assembled rather than judged here for the same reason authorship is: a script cannot look
    at an image. The agent can, and it holds the brand pack and the surrounding components while it
    does. So the machinery states WHAT must be judged and records the verdict; the judgement is the
    agent's, and `--verdict` is where it comes back.

    A surface with no stated acceptance check yields no brief, because a critic with no criterion
    produces an opinion, and an opinion recorded as a verdict is worse than no verdict at all.
    """
    config = load_config(root)
    approval = decide(root, request)                 # RE-RUN: the same gate, no shortcuts
    surface = approval["provenance"]["surface"]
    criterion = (config.get("acceptance") or {}).get(surface)
    if not criterion:
        raise Refusal(
            f"no acceptance check stated for {surface!r}, so there is nothing to judge this against. "
            f"Write one in `acceptance` — a critic with no criterion produces an opinion, and an "
            f"opinion recorded as a verdict is worse than no verdict.")
    brief = (config.get("briefs") or {}).get(surface, {})
    return {
        "asset": _project_relative(asset.resolve(), root),
        "surface": surface,
        "kind": approval["provenance"].get("kind", "static"),
        "acceptance": criterion,
        "brief": {k: brief.get(k) for k in ("style", "subject", "mood")},
        "pack": request.get("pack", {}),
        "prompt": approval["prompt"],
        "judge": ("Look at the asset. Does it meet the acceptance check, in the stated style, on "
                  "this pack's palette? Answer accept or reject with one sentence of why — and "
                  "reject on a near miss, because the next rung costs less than a surface that "
                  "reads as almost-right forever."),
        "then": "re-run with --verdict accept|reject --why '<one sentence>'",
    }


def record_verdict(root: Path, request: dict, asset: Path, verdict: str, why: str) -> dict:
    """Accept -> the manifest. Reject -> the NEXT rung, or an honest stop.

    The reject path is what makes `attempt` mean something: a rejected asset increments it, so the
    next run climbs -- which is the only trigger the ladder ever had, and it was never wired.
    """
    if verdict not in VERDICTS:
        raise Unusable(f"verdict must be one of {', '.join(VERDICTS)}; got {verdict!r}")
    if not why.strip():
        raise Unusable("a verdict needs a reason. `accept` with no reason cannot be reviewed later, "
                       "and `reject` with no reason cannot be acted on.")
    config = load_config(root)
    approval = decide(root, request)
    prov = approval["provenance"]
    if verdict == "accept":
        entry = {**manifest_entry(root, config, prov, asset.resolve()), "accepted_because": why}
        out = {"verdict": "accept", "manifest": str(append_manifest(root, entry)), "why": why}
        warning = remember_prompt(root, config, prov, approval["prompt"],
                                  asset=_project_relative(asset, root), model=None,
                                  verdict="accept", why=why)
        if warning:
            out["prompt_library_warning"] = warning
        return out
    # A REJECTED PROMPT IS RECORDED TOO, and that is the half worth defending. A library holding
    # only the keepers cannot answer "did we already try this and hate it?", so the next run
    # re-buys the prompt that failed -- paying for the same disappointment twice.
    warning = remember_prompt(root, config, prov, approval["prompt"], asset=None, model=None,
                              verdict="reject", why=why)
    return {
        "verdict": "reject", "why": why,
        **({"prompt_library_warning": warning} if warning else {}),
        "next_attempt": int(request.get("attempt", 0)) + 1,
        "then": ("re-run the request with `attempt` incremented to climb to the next rung. If the "
                 "ladder is exhausted the gate says so rather than re-buying the same rung — a "
                 "reroll at the same rung is the reroll a composed prompt exists to avoid."),
    }


def _project_relative(out: Path, root: Path) -> str:
    try:
        return str(out.resolve().relative_to(root.resolve()))
    except ValueError:
        raise Unusable(f"{out} is outside the project ({root}); a manifest path must be relative "
                       f"or it is broken for everyone who clones the repository.")


def manifest_entry(root: Path, config: dict, prov: dict, out: Path) -> dict:
    """Build one COMPLETE manifest row. Both the bought and the agent-authored paths use this.

    `kind` comes from the provenance, not from a caller's local: it was a local when this lived
    inside produce(), and factoring it out left a NameError that only fired on the agent path --
    the one path with no test yet.
    """
    brief = (config.get("briefs") or {}).get(prov["surface"], {})
    kind = prov.get("kind", "static")
    return {
        # `relative_to` raises on a path outside the project, and a manifest holding an absolute
        # path is broken for everyone else who clones. Refuse rather than record either.
        "file": _project_relative(out, root),
        "name": brief.get("subject") or prov["surface"],
        "purpose": brief.get("purpose") or f"carry the {prov['surface']} surface",
        "use_cases": brief.get("use_cases") or [prov["surface"]],
        "avoid": brief.get("avoid") or ["any surface with its own stated asset"],
        "visual_elements": brief.get("subject", ""),
        "style": brief.get("style", ""),
        "kind": kind,
        "surface": prov["surface"],
    }



MAX_FETCH_BYTES = 64 * 1024 * 1024


def agent_target(root: Path, prov: dict, ext: str | None = None) -> Path:
    """Where an agent-authored asset goes. One namer, so the brief and the ingest cannot disagree.

    `ext` is passed by the ingest path, which has the BYTES and therefore knows the real format;
    when it is None the extension is guessed from `kind`, which is all the brief can do — it names
    the target before anything has been generated.
    """
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{prov['surface']}-agent").strip("-")
    suffix = ext or {"vector": "svg", "motion": "json", "video": "mp4"}.get(
        prov.get("kind"), "png")
    return root / ASSET_LIBRARY / f"{stem}.{suffix}"


def fetch_url(url: str, timeout: int) -> bytes:
    """Download the bytes an image MCP handed back as a URL.

    THE SCHEME CHECK IS NOT A FORMALITY. `--from-url` takes a string an agent read out of a tool
    result, and `file:///etc/passwd` is a URL `urlopen` will happily open -- after which the gate's
    format sniff decides whether a local secret gets written into `docs/assets/` and committed. Only
    http(s) is ever fetched.
    """
    scheme = url.split(":", 1)[0].lower() if ":" in url else ""
    if scheme not in ("http", "https"):
        raise Unusable(f"refusing to fetch {url!r}: only http and https are fetched. A `file:` or "
                       f"`data:` URL would read this machine rather than the provider, and the "
                       f"result would be committed into docs/assets as though a model had made it.")
    try:
        # CONSTRUCTED INSIDE THE TRY. `Request.__init__` parses the URL, so a malformed one raises
        # ValueError HERE rather than at `urlopen` -- and built outside, that is an uncaught
        # traceback instead of a refusal. The mutation guard for the scheme check found this.
        req = urllib.request.Request(url, headers={"User-Agent": "design-flow/generate_asset"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310 - scheme checked
            blob = resp.read(MAX_FETCH_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise Unusable(f"the asset URL returned HTTP {exc.code}. Nothing was saved. If the provider "
                       f"signs its URLs these expire quickly — re-read the tool result rather than "
                       f"re-generating, which would bill you a second time.")
    # ValueError is NOT an OSError, and `urlopen` raises it for a malformed URL ("unknown url
    # type"). Left out, a mistyped URL is an uncaught traceback rather than a refusal -- and a
    # traceback is not a verdict, so nothing downstream can tell a bad URL from a broken script.
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise Unusable(f"could not fetch the asset URL ({exc}). Nothing was saved.")
    if not blob:
        raise Unusable(f"{url} returned no bytes. An empty download is not an asset, and recording "
                       f"it would put a 0-byte file in the manifest as though it were art.")
    if len(blob) > MAX_FETCH_BYTES:
        raise Unusable(f"{url} is larger than {MAX_FETCH_BYTES // (1024 * 1024)} MB. Refusing rather "
                       f"than committing it: an asset that size is a mistake, not a decision.")
    return blob


def remember_prompt(root: Path, config: dict, prov: dict, prompt: str, **kw) -> str | None:
    """Record the prompt in the library. Returns a WARNING string on failure — never raises.

    Neither swallowed nor raised, and both halves are deliberate:

      - RAISING would report a run that bought and saved an asset as a failure, because a
        bookkeeping step complained afterwards. That is #627 exactly — a paid success thrown away
        by a later step — and re-introducing it here, in the module written to make spending
        legible, would be a poor joke.
      - SWALLOWING would leave the library quietly incomplete, which is the claims-vs-enforcement
        defect this module exists to close. A store nobody can trust to be complete is not a store.

    So the run succeeds AND says the record is missing, and the caller prints it where the operator
    is already looking.
    """
    brief = (config.get("briefs") or {}).get(prov["surface"], {})
    try:
        prompt_library.upsert(root, prompt_library.build_entry(prov, prompt, brief, **kw))
    except (prompt_library.Unusable, OSError) as why:
        return (f"the asset is saved, but the prompt could NOT be recorded in "
                f"{prompt_library.LIBRARY_PATH}: {why}. Reproducing this asset now means "
                f"reconstructing the prompt by hand, or paying for it again.")
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--request", help="path to a JSON request, or - for stdin")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--record", metavar="FILE",
                    help="register a file the AGENT authored, after the gate approved it")
    ap.add_argument("--model", metavar="ID", default=None,
                    help="the model that ACTUALLY rendered a --record'ed asset (e.g. "
                         "gemini-2.5-flash-image). The `agent` rung is a role, not a model, so "
                         "without this the prompt library records the model as unknown rather "
                         "than guessing.")
    ap.add_argument("--from-url", metavar="URL", default=None,
                    help="download an asset the provider returned as a URL and record it. For image "
                         "MCPs that hand back a link rather than a file — the agent cannot write "
                         "bytes it only saw rendered, but it CAN read a URL.")
    ap.add_argument("--spent", type=float, metavar="USD", default=None,
                    help="what a --record'ed asset actually cost, when the agent paid a provider "
                         "the flow did not call itself. Omitted means nothing was spent here.")
    ap.add_argument("--critique", metavar="FILE",
                    help="emit what a critic needs to judge FILE against its acceptance check")
    ap.add_argument("--verdict", choices=VERDICTS, help="record a critic's decision on --critique")
    ap.add_argument("--why", default="", help="one sentence behind the verdict; required")
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
        if args.critique and args.verdict:
            print(json.dumps(record_verdict(Path.cwd(), request, Path(args.critique),
                                            args.verdict, args.why), indent=2))
            return 0
        if args.critique:
            print(json.dumps(critique_brief(Path.cwd(), request, Path(args.critique)), indent=2))
            return 0
        if args.from_url:
            # #628. THE AGENT CANNOT WRITE BYTES IT ONLY SAW RENDERED. An image MCP that returns an
            # inline image block hands the agent a picture, not base64 it can faithfully retype, so
            # `--record <path>` dead-ends after the provider has already billed. A URL is different
            # in exactly the way that matters: it is TEXT the agent can read out of the tool result
            # and pass on, and the script does the fetching. Same gate, same sniff, same manifest --
            # this is an ingest, not a bypass.
            root = Path.cwd()
            approval = decide(root, request)
            prov = approval["provenance"]
            blob = fetch_url(args.from_url, args.timeout)
            ext = assert_kind_matches(prov.get("kind", "static"), blob)
            assert_aspect(blob, prov.get("aspect"))
            written = agent_target(root, prov, ext)
            written.parent.mkdir(parents=True, exist_ok=True)
            written.write_bytes(blob)
            config = load_config(root)
            manifest = append_manifest(root, manifest_entry(root, config, prov, written.resolve()))
            warning = remember_prompt(root, config, prov, approval["prompt"],
                                      asset=_project_relative(written, root), model=args.model,
                                      actual_cost_usd=args.spent)
            out = {"recorded": str(written), "bytes": len(blob), "source": args.from_url,
                   "manifest": str(manifest),
                   "prompts": str(root / prompt_library.LIBRARY_PATH)}
            if args.model is None:
                out["model"] = ("unknown — recorded as such. Pass --model to state which model the "
                                "MCP actually called.")
            if warning:
                out["prompt_library_warning"] = warning
            print(json.dumps(out, indent=2))
            return 0
        if args.record:
            # Re-run the gate here too. An agent-authored asset gets NO easier route into the
            # manifest than a bought one -- otherwise "the agent wrote it" becomes the way past
            # every refusal, which is the forged-approval hole wearing a friendlier name.
            root = Path.cwd()
            approval = decide(root, request)
            written = Path(args.record)
            if not written.is_file():
                print(f"cannot record: {written} does not exist", file=sys.stderr)
                return 2
            blob = written.read_bytes()
            assert_kind_matches(approval["provenance"].get("kind", "static"), blob)
            assert_aspect(blob, approval["provenance"].get("aspect"))
            config = load_config(root)
            entry = manifest_entry(root, config, approval["provenance"], written.resolve())
            manifest = append_manifest(root, entry)
            warning = remember_prompt(root, config, approval["provenance"], approval["prompt"],
                                      asset=_project_relative(written, root), model=args.model,
                                      actual_cost_usd=args.spent)
            out = {"recorded": str(written), "bytes": len(blob), "manifest": str(manifest),
                   "prompts": str(root / prompt_library.LIBRARY_PATH)}
            if args.model is None:
                out["model"] = ("unknown — recorded as such. The `agent` rung names who did the "
                                "work, not what rendered it; pass --model to state the real one.")
            if warning:
                out["prompt_library_warning"] = warning
            print(json.dumps(out, indent=2))
            return 0
        print(json.dumps(produce(Path.cwd(), request, args.timeout), indent=2))
        return 0
    except AgentWrites as brief:
        print(json.dumps({
            "approved": True,
            "author": "agent",
            "write_to": str(brief.target),
            "prompt": brief.prompt,
            # #628. CHECK THE RESPONSE SHAPE BEFORE YOU CALL, not after you are billed. A provider
            # that returns the image INLINE hands the agent a rendered picture -- not base64 it can
            # retype -- so there is no route from that result to a file, and the money is gone. This
            # list is the whole fix: it turns a $0.04 dead-end into a decision made beforehand.
            "before_you_spend": {
                "check": "Which shape does your image MCP return? Decide BEFORE calling it — after "
                         "the call you have been billed either way.",
                "a file path": f"call it, then: --record <that path> (or move it to {brief.target})",
                "a URL": "call it, then: --from-url <that URL> — the script downloads it, because "
                         "a URL is text you can read and pass on",
                "the image INLINE only": "STOP. Do NOT call it. You cannot save an image you only "
                                         "saw rendered — you cannot faithfully transcribe its "
                                         "bytes, and neither can any other model. The generation "
                                         "would succeed, bill you, and leave nothing to record. "
                                         "Configure a keyed REST rung (`aggregator: openrouter` "
                                         "with an API key) so the SCRIPT makes the call and writes "
                                         "the bytes itself.",
                "you author it yourself (SVG)": f"write it to {brief.target}, then --record it",
            },
            "then": (f"python3 {Path(__file__).name} --request <req> --record {brief.target} "
                     f"--model <the model you actually called> --spent <usd>"),
            "or": (f"python3 {Path(__file__).name} --request <req> --from-url <url> "
                   f"--model <model> --spent <usd>"),
            "note": ("--model and --spent are what make the prompt library worth reading. The "
                     "`agent` rung says who did the work, not what rendered it, so without "
                     "--model the entry records the model as unknown — honest, but it cannot "
                     "answer 'which model made the good one?' later."),
        }, indent=2))
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

    # THE .env FILE. Two shipped messages promised this worked while nothing read the file, so a
    # user who followed the instruction got "not set" and reasonably concluded the tool was broken.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        os.environ.pop("DF_ENV_KEY", None)
        (root / ".env").write_text(
            "# a comment\n\nexport DF_ENV_KEY='sk-from-dotenv'\nOTHER=x\n", encoding="utf-8")
        check("a key in .env is found", preflight_key("DF_ENV_KEY", root) == "sk-from-dotenv")
        check("...quotes are stripped", "'" not in preflight_key("DF_ENV_KEY", root))
        check("...and an unrelated key is not returned",
              dotenv_value(root, "MISSING") is None)
        # The real environment WINS: a shell export is the more deliberate act, and someone
        # debugging a key must not be silently overridden by a stale file.
        os.environ["DF_ENV_KEY"] = "sk-from-shell"
        check("the environment beats .env", preflight_key("DF_ENV_KEY", root) == "sk-from-shell")
        os.environ.pop("DF_ENV_KEY", None)
        # A PLACEHOLDER in .env is still a placeholder -- the file is a source, not an exemption.
        (root / ".env").write_text("DF_ENV_KEY=your-api-key\n", encoding="utf-8")
        try:
            preflight_key("DF_ENV_KEY", root)
            failures.append("a placeholder in .env should still refuse")
        except Refusal as exc:
            check("a placeholder in .env still refuses", "PLACEHOLDER" in str(exc))
        checks += 1
    with tempfile.TemporaryDirectory() as td:
        os.environ.pop("DF_ENV_KEY", None)
        try:
            preflight_key("DF_ENV_KEY", Path(td))
            failures.append("no .env and no env var should refuse")
        except Refusal as exc:
            check("no .env and no env var still refuses", "not set" in str(exc))
        checks += 1
    # Called WITHOUT a root (the old signature) must not crash -- the selftest above uses it.
    os.environ.pop("DF_ENV_KEY", None)
    try:
        preflight_key("DF_ENV_KEY")
        failures.append("no root should still refuse, not crash")
    except Refusal:
        pass
    checks += 1

    # THE GATE IS RE-RUN. A forged approval must not reach the provider -- this is the property that
    # makes every refusal in generation_gate.py binding rather than advisory.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".design-flow").mkdir()
        (root / ".design-flow/generation.json").write_text(json.dumps({
            "aggregator": "no-such-provider", "api_key_env": "DF_TEST_KEY", "budget_usd": 1.0,
            "ladder": [{"name": "m", "cost_usd": 0.01}],
            "briefs": {"s": {"style": "flat-vector", "subject": "x", "mood": "calm",
                             "palette": ["monochrome"]}},
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

    # THE AGENT PATH. Claude Code writes SVG natively and already holds the brand pack, the token
    # names and the surrounding components -- context a remote model does not have. So for vector
    # work the external call buys a worse result at a cost. The GATE still runs in full; only the
    # HTTP request is skipped, because the discipline was never the request.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".design-flow").mkdir()
        (root / ".design-flow/generation.json").write_text(json.dumps({
            "aggregator": "agent", "budget_usd": 1.0,
            "ladders": {"vector": [{"name": "agent", "cost_usd": 0.0}]},
            "briefs": {"s": {"style": "flat-vector", "subject": "a tray", "mood": "light",
                             "palette": ["monochrome"]}},
        }), encoding="utf-8")
        req = {"kind": "vector",
               "tier_refusal": {"surface": "s", "tier_1_why_not": "a", "tier_2_why_not": "b"},
               "pack": {"variant": "default"}}
        # NO KEY IS SET, and none is needed -- the adapter is resolved before the preflight, which
        # it was not at first: the one path that never calls an API demanded a credential for it.
        os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            produce(root, req)
            failures.append("the agent path should hand back a brief, not produce")
        except (Refusal, Unusable) as why:
            failures.append(f"the agent path needs no API key (refused instead: {why})")
        except AgentWrites as brief:
            check("the agent path handed back a brief", True)
            check("...and names a target inside the project",
                  str(brief.target).startswith(str(root)))
            check("...with the composed prompt, not a free-typed one",
                  "flat-vector" in brief.prompt and "a tray" in brief.prompt)
        checks += 3
        # An agent-authored file gets NO easier route into the manifest: a raster is still refused.
        target = root / ASSET_DIR / "s-agent.svg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\x89PNG\r\n\x1a\n")
        checks += 1
        try:
            assert_kind_matches("vector", target.read_bytes())
            failures.append("a raster recorded as vector is still refused")
        except Unusable:
            pass
        check("...and a raster as `static` is fine",
              assert_kind_matches("static", target.read_bytes()) == "png")
        target.write_text("<svg viewBox='0 0 1 1'></svg>", encoding="utf-8")
        check("...and real SVG bytes sniff as svg",
              sniff_extension(target.read_bytes()) == "svg")
        # A real test, not `__name__ == "..."` -- which is what this line was first, and could
        # not fail. A manifest holding an absolute path is broken for everyone who clones.
        checks += 1
        try:
            _project_relative(Path("/etc/hosts"), root)
            failures.append("a path outside the project should be refused")
        except Unusable:
            pass
        check("...while a path inside it resolves relative",
              _project_relative(root / "docs/assets/x.svg", root) == "docs/assets/x.svg")

    # THE CRITIC. `acceptance` was a string that had to be PRESENT before the ladder could climb --
    # letter of the criterion, not spirit: nothing read the asset, so the climb trigger was one
    # nobody could pull, and `attempt` existed while nothing ever set it.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".design-flow").mkdir()
        cfg = {"aggregator": "agent", "budget_usd": 1.0,
               "ladders": {"static": [{"name": "agent", "cost_usd": 0.0},
                                      {"name": "better", "cost_usd": 0.5}]},
               "briefs": {"s": {"style": "flat-vector", "subject": "a tray", "mood": "light",
                             "palette": ["monochrome"]}},
               "acceptance": {"s": "reads as the brand at a glance"}}
        (root / ".design-flow/generation.json").write_text(json.dumps(cfg), encoding="utf-8")
        (root / ASSET_DIR).mkdir(parents=True)
        asset = root / ASSET_DIR / "s.svg"
        asset.write_text("<svg viewBox='0 0 1 1'></svg>", encoding="utf-8")
        req = {"kind": "static", "pack": {"variant": "default"},
               "library_miss": {"searched_for": "a tray", "why_no_fit": "library is empty"},
               "tier_refusal": {"surface": "s", "tier_1_why_not": "a", "tier_2_why_not": "b"}}

        brief = critique_brief(root, req, asset)
        check("the critique brief carries the acceptance check",
              brief["acceptance"] == "reads as the brand at a glance")
        check("...and the brief it was generated from", brief["brief"]["style"] == "flat-vector")
        check("...and the asset path, relative", brief["asset"].startswith("docs/assets"))
        # A criterion is REQUIRED: a critic without one produces an opinion, and an opinion
        # recorded as a verdict is worse than no verdict.
        checks += 1
        nocrit = {**cfg, "acceptance": {}}
        (root / ".design-flow/generation.json").write_text(json.dumps(nocrit), encoding="utf-8")
        try:
            critique_brief(root, req, asset)
            failures.append("a surface with no acceptance check should refuse to be critiqued")
        except Refusal:
            pass
        (root / ".design-flow/generation.json").write_text(json.dumps(cfg), encoding="utf-8")

        # REJECT increments the attempt -- the only trigger the ladder ever had, now wired.
        rej = record_verdict(root, req, asset, "reject", "reads as stock")
        check("reject climbs to the next rung", rej["next_attempt"] == 1)
        check("...and keeps the reason", rej["why"] == "reads as stock")


        # A REJECTED PROMPT IS IN THE LIBRARY. Recording only the keepers would leave the next run
        # unable to see that this prompt was already tried and disliked, so it re-buys the same
        # disappointment -- the exact re-spend the library exists to make visible.
        lib = prompt_library.load(root)["prompts"]
        check("reject records the prompt", len(lib) == 1)
        # Read through a default rather than `lib[0]`: with the row missing, indexing raises and the
        # run dies before printing the failure above -- and a crash is not a verdict. The mutation
        # guard for this exact line found that, reporting the catch as coincidental.
        row = lib[0] if lib else {}
        check("...as rejected", row.get("verdict") == "reject")
        check("...carrying the reason", row.get("why") == "reads as stock")
        check("...and the prompt verbatim", row.get("prompt") == decide(root, req)["prompt"])

        # ACCEPT writes the manifest, with the reason attached for a later reader.
        acc = record_verdict(root, req, asset, "accept", "on brand at a glance")
        check("accept writes the manifest", Path(acc["manifest"]).is_file())
        check("...recording why it was accepted",
              json.loads((root / ASSET_DIR / "manifest.json").read_text())
                  ["assets"][-1]["accepted_because"] == "on brand at a glance")
        # The SAME prompt judged twice is ONE library row whose verdict moved, not two rows. Two
        # rows would read as two prompts, and the reject would go on warning about a prompt that
        # was subsequently accepted.
        lib = prompt_library.load(root)["prompts"]
        check("a re-judged prompt stays one row", len(lib) == 1)
        check("...whose verdict moved to accept", lib[0]["verdict"] == "accept")
        check("...and now names the asset it kept", lib[0]["asset"].startswith("docs/assets"))
        # A verdict with no reason is refused in BOTH directions: an accept nobody can review is
        # as useless as a reject nobody can act on.

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".design-flow").mkdir()
        (root / ".design-flow/generation.json").write_text(json.dumps(cfg), encoding="utf-8")
        (root / ASSET_DIR).mkdir(parents=True)
        asset = root / ASSET_DIR / "s.svg"
        asset.write_text("<svg viewBox='0 0 1 1'></svg>", encoding="utf-8")
        for v in VERDICTS:
            checks += 1
            try:
                record_verdict(root, req, asset, v, "   ")
                failures.append(f"a {v} verdict with no reason should be refused")
            except (Unusable, Refusal) as exc:
                if "reason" not in str(exc):
                    failures.append(f"a {v} verdict with no reason should be refused "
                                    f"for that reason, not: {exc}")

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

    # THE pen RUNG (#599). A local CLI, so it takes no key -- and the absent-binary path is the
    # state of most machines, including the one this was written on.
    check("pen is a registered adapter", ADAPTERS.get("pen") is call_pen)
    check("...and is keyless, like the agent", {"agent", "pen"} <= KEYLESS)
    check("...while a paying adapter is NOT keyless", not (KEYLESS & {"openrouter", "gemini"}))
    import shutil as _sh
    real_which = _sh.which
    try:
        _sh.which = lambda _name: None                       # the binary is absent
        try:
            call_pen("", "pen", "a composed prompt", None, 5)
            failures.append("an absent `pen` binary should refuse")
        except Unusable as exc:
            msg = str(exc)
            # SAY ONLY WHAT A PATH MISS PROVES. pen.dev also ships as a user-scoped MCP server, so a
            # provisioned machine can fail this probe -- measured. Claiming "pen.dev is not
            # installed" would send someone to install what they already have.
            check("an absent binary refuses", "not on PATH" in msg)
            check("...naming the install command", "npm install -g @pen.dev/cli" in msg)
            check("...without claiming pen.dev itself is absent",
                  "MCP server" in msg and "pen.dev is not installed" not in msg)
            check("...and stating nothing was spent", "Nothing was spent" in msg)
        checks += 1
        # A CLI that exits non-zero must surface ITS OWN stderr. Paraphrasing a tool's refusal into
        # "generation failed" is how a fixable auth problem reads like a provider outage.
        _sh.which = lambda _name: "/usr/bin/true"
        import subprocess as _sp
        real_run = _sp.run
        try:
            _sp.run = lambda *a, **k: _sp.CompletedProcess([], 3, "", "not logged in")
            try:
                call_pen("", "pen", "p", None, 5)
                failures.append("a non-zero pen exit should refuse")
            except Unusable as exc:
                check("a failing CLI surfaces its own stderr verbatim", "not logged in" in str(exc))
            checks += 1
            # EXIT 0 WITH NO ARTEFACT IS NOT A COMPLETION -- the same rule the plan applies to rows.
            _sp.run = lambda *a, **k: _sp.CompletedProcess([], 0, "", "")
            try:
                call_pen("", "pen", "p", None, 5)
                failures.append("exit 0 with no image should refuse")
            except Unusable as exc:
                check("exit 0 with no image is refused, not recorded",
                      "wrote no image" in str(exc))
            checks += 1
        finally:
            _sp.run = real_run
    finally:
        _sh.which = real_which

    # THE `--record` PATH END TO END, through the real CLI. This is the path #627 landed on -- an
    # agent authored an asset, could not see where to put it, and the paid result was thrown away --
    # and it is the path where the model is a ROLE rather than a model, so it is the one place the
    # library can most easily start lying. Driving the argv rather than calling the function tests
    # the flags too, which is where `--model` and `--spent` actually live.
    with tempfile.TemporaryDirectory() as td:
        import subprocess as _sp
        root = Path(td)
        (root / ".design-flow").mkdir()
        (root / ".design-flow/generation.json").write_text(json.dumps({
            "aggregator": "agent", "budget_usd": 1.0,
            "ladders": {"vector": [{"name": "agent", "cost_usd": 0.0}]},
            "briefs": {"s": {"style": "flat-vector", "subject": "a tray", "mood": "light",
                             "palette": ["monochrome"], "use_cases": ["the s surface"],
                             "avoid": ["stock photography"]}},
        }), encoding="utf-8")
        # `library_miss` is stated up front because the FIRST --record writes a manifest, and from
        # that moment `docs/assets` is a curated library the gate requires every later request to
        # search. Discovered by this fixture: without it the second call refuses, correctly.
        req = {"kind": "vector", "pack": {"variant": "default"},
               "library_miss": {"searched_for": "a tray", "why_no_fit": "nothing depicts one"},
               "tier_refusal": {"surface": "s", "tier_1_why_not": "a", "tier_2_why_not": "b"}}
        (root / "req.json").write_text(json.dumps(req), encoding="utf-8")
        (root / ASSET_DIR).mkdir(parents=True)
        art = root / ASSET_DIR / "s-agent.svg"
        art.write_text("<svg viewBox='0 0 1 1'></svg>", encoding="utf-8")

        def record(*extra: str):
            return _sp.run([sys.executable, str(Path(__file__).resolve()), "--request", "req.json",
                            "--record", str(art), *extra],
                           cwd=root, capture_output=True, text=True, timeout=60)

        proc = record()
        check(f"--record succeeds (exit {proc.returncode})", proc.returncode == 0)
        out = json.loads(proc.stdout or "{}")
        check("...and names the prompt library it wrote", "prompts" in out)
        check("...and says the model is unknown rather than guessing",
              "unknown" in out.get("model", ""))
        check("...with nothing swallowed", "prompt_library_warning" not in out)
        lib = prompt_library.load(root)["prompts"]
        check("the agent path records the prompt", len(lib) == 1)
        # THE HEADLINE ASSERTION. `agent` is who did the work; recording it under `model` would
        # answer "which model made this?" with a role name, and reuse decisions are made from that
        # column. Null is the honest value and this is what pins it.
        check("...with model NULL, never the rung name", lib[0]["model"] is None)
        check("...saying why it is null", "role, not a model" in (lib[0]["model_note"] or ""))
        check("...keeping the rung separately", lib[0]["rung"] == "agent")
        check("...the prompt verbatim", "flat-vector" in lib[0]["prompt"])
        check("...the brief's use cases", lib[0]["use_cases"] == ["the s surface"])
        check("...the brief's avoid list", lib[0]["avoid"] == ["stock photography"])
        check("...the asset it produced", lib[0]["asset"] == "docs/assets/s-agent.svg")
        check("...and nothing spent, because nothing was", lib[0]["spent_total_usd"] == 0.0)

        # RECORDING THE SAME SURFACE TWICE IS REFUSED, and finding that out here is the point of
        # driving the real CLI: a surface that already has an asset must not quietly acquire a
        # second one, because that forks its look with nothing to say which is current. So the
        # library's accumulate-on-re-spend behaviour is NOT reachable by re-recording -- it is
        # reached by reject -> climb -> re-buy, which needs a provider and is therefore asserted
        # directly in `prompt_library.py --selftest` instead of pretended at here.
        proc = record()
        check(f"a second record for one surface is refused (exit {proc.returncode})",
              proc.returncode == 1)
        check("...saying the surface already has one",
              "already lists" in json.loads(proc.stdout or "{}").get("refused", ""))

        # STATING the model is what makes the column worth reading, so assert it on a surface
        # entitled to its own asset.
        cfg2 = json.loads((root / ".design-flow/generation.json").read_text(encoding="utf-8"))
        cfg2["briefs"]["t"] = {**cfg2["briefs"]["s"], "subject": "a lamp"}
        (root / ".design-flow/generation.json").write_text(json.dumps(cfg2), encoding="utf-8")
        req2 = {**req, "tier_refusal": {**req["tier_refusal"], "surface": "t"}}
        (root / "req2.json").write_text(json.dumps(req2), encoding="utf-8")
        art2 = root / ASSET_DIR / "t-agent.svg"
        art2.write_text("<svg viewBox='0 0 1 1'></svg>", encoding="utf-8")
        proc = _sp.run([sys.executable, str(Path(__file__).resolve()), "--request", "req2.json",
                        "--record", str(art2), "--model", "gemini-2.5-flash-image",
                        "--spent", "0.04"],
                       cwd=root, capture_output=True, text=True, timeout=60)
        check(f"--record --model succeeds (exit {proc.returncode})", proc.returncode == 0)
        check("...and stops calling the model unknown",
              "model" not in json.loads(proc.stdout or "{}"))
        rows = {r["surface"]: r for r in prompt_library.load(root)["prompts"]}
        check("a stated model is recorded as the model", rows["t"]["model"] == "gemini-2.5-flash-image")
        check("...with no excuse note", rows["t"]["model_note"] is None)
        check("...and the spend it declared", rows["t"]["spent_total_usd"] == 0.04)
        check("...leaving the earlier unknown alone", rows["s"]["model"] is None)

        # THE VIEW is opt-in, and held current once it exists -- the `plan.md` contract exactly.
        check("no view means no drift complaint", prompt_library.check(root) == [])
        rc = _sp.run([sys.executable,
                      str(Path(__file__).resolve().parent / "prompt_library.py"), "--render"],
                     cwd=root, capture_output=True, text=True, timeout=60)
        check(f"--render writes the view (exit {rc.returncode})",
              rc.returncode == 0 and (root / prompt_library.RENDER_PATH).is_file())
        check("...which is clean immediately after", prompt_library.check(root) == [])
        view = (root / prompt_library.RENDER_PATH).read_text(encoding="utf-8")
        check("...naming the known model", "gemini-2.5-flash-image" in view)
        check("...and flagging the unknown one rather than printing the rung",
              "**unknown**" in view and "| `agent` |" not in view)
        check("...and totalling the spend", "$0.04 spent in total" in view)

        # A RECORD AFTER THE VIEW EXISTS must refresh it. The re-render lives at the store's choke
        # point precisely so a path added later cannot forget, and this is what pins that.
        cfg2["briefs"]["u"] = {**cfg2["briefs"]["s"], "subject": "a chair"}
        (root / ".design-flow/generation.json").write_text(json.dumps(cfg2), encoding="utf-8")
        (root / "req3.json").write_text(
            json.dumps({**req, "tier_refusal": {**req["tier_refusal"], "surface": "u"}}),
            encoding="utf-8")
        art3 = root / ASSET_DIR / "u-agent.svg"
        art3.write_text("<svg viewBox='0 0 1 1'></svg>", encoding="utf-8")
        _sp.run([sys.executable, str(Path(__file__).resolve()), "--request", "req3.json",
                 "--record", str(art3)], cwd=root, capture_output=True, text=True, timeout=60)
        check("a later record REFRESHED the committed view rather than staling it",
              prompt_library.check(root) == [])
        check("...and the view grew a row", len(prompt_library.load(root)["prompts"]) == 3)

    # #628. THE URL INGEST. The agent cannot write bytes it only saw rendered, so a URL is the one
    # provider response shape it CAN act on -- a URL is text. Nothing here reaches the network: the
    # fetch is stubbed, because a test that needed a provider would be a bill, not a test.
    with tempfile.TemporaryDirectory() as td:
        import subprocess as _sp
        root = Path(td)
        (root / ".design-flow").mkdir()
        (root / ".design-flow/generation.json").write_text(json.dumps({
            "aggregator": "agent", "budget_usd": 1.0,
            "ladders": {"static": [{"name": "agent", "cost_usd": 0.04}]},
            "briefs": {"s": {"style": "flat-vector", "subject": "a tray", "mood": "light",
                             "palette": ["monochrome"]}},
        }), encoding="utf-8")
        req = {"kind": "static", "pack": {"variant": "default"},
               "tier_refusal": {"surface": "s", "tier_1_why_not": "a", "tier_2_why_not": "b"}}
        (root / "req.json").write_text(json.dumps(req), encoding="utf-8")

        # ONLY http(s) IS EVER FETCHED, and this is not a formality: `--from-url` takes a string an
        # agent read out of a tool result, so a `file:` URL would read this machine and commit the
        # result into docs/assets as though a model had made it.
        for bad in ("file:///etc/passwd", "data:image/png;base64,AAAA", "/etc/passwd"):
            checks += 1
            try:
                fetch_url(bad, 5)
                failures.append(f"{bad} should be refused; only http(s) is fetched")
            except Unusable as exc:
                if "only http and https" not in str(exc):
                    failures.append(f"{bad} refused for the wrong reason: {exc}")

        real_urlopen = urllib.request.urlopen
        try:
            png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

            class _Resp:
                def __init__(self, blob): self._b = blob
                def read(self, _n=None): return self._b
                def __enter__(self): return self
                def __exit__(self, *a): return False

            # AN EMPTY DOWNLOAD IS NOT AN ASSET. Recording it would put a 0-byte file in the
            # manifest as though it were art -- a "done" row nobody can see is wrong.
            urllib.request.urlopen = lambda *a, **k: _Resp(b"")
            checks += 1
            try:
                fetch_url("https://example.invalid/x.png", 5)
                failures.append("an empty download should be refused")
            except Unusable as exc:
                if "no bytes" not in str(exc):
                    failures.append(f"an empty download refused for the wrong reason: {exc}")

            urllib.request.urlopen = lambda *a, **k: _Resp(png)
            blob = fetch_url("https://example.invalid/x.png", 5)
            check("a fetched blob comes back whole", blob == png)
            check("...and sniffs as what it is", assert_kind_matches("static", blob) == "png")
            # THE FORMAT IS SNIFFED FROM THE BYTES, so a URL claiming .svg that serves PNG is
            # refused rather than written to a filename that lies about its contents.
            checks += 1
            try:
                assert_kind_matches("vector", blob)
                failures.append("a raster fetched for a vector row should be refused")
            except Unusable:
                pass
            check("the ingest target is the agent target, with the SNIFFED extension",
                  agent_target(root, {"surface": "s", "kind": "static"}, "png").name
                  == "s-agent.png")
            check("...and the brief's target guesses from kind when there are no bytes yet",
                  agent_target(root, {"surface": "s", "kind": "vector"}).name == "s-agent.svg")
        finally:
            urllib.request.urlopen = real_urlopen

        # THE INGEST END TO END, through the real CLI, over a REAL socket -- served from localhost
        # so nothing leaves the machine and no provider is billed. Stubbing `urlopen` in-process
        # would have left the subprocess path (gate -> fetch -> sniff -> write -> manifest ->
        # library) untested, and that whole chain is what #628 asked for.
        import http.server
        import threading

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):                                    # noqa: N802 - stdlib's spelling
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png)))
                self.end_headers()
                self.wfile.write(png)

            def log_message(self, *a):                           # keep the selftest output clean
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_port}/x.png"
            proc = _sp.run([sys.executable, str(Path(__file__).resolve()), "--request", "req.json",
                            "--from-url", url, "--model", "seedream-4.5", "--spent", "0.04"],
                           cwd=root, capture_output=True, text=True, timeout=60)
            check(f"--from-url records end to end (exit {proc.returncode})", proc.returncode == 0)
            out = json.loads(proc.stdout or "{}")
            check("...writing the file the agent could not write itself",
                  (root / ASSET_LIBRARY / "s-agent.png").is_file())
            check("...with the fetched bytes intact",
                  (root / ASSET_LIBRARY / "s-agent.png").read_bytes() == png)
            # #625/#628/#629. THE NEGATIVE HALF: the flat root is where every asset used to land,
            # so "it is in the library folder" is only half a check — a path that wrote to BOTH, or
            # that fell back to the root on some branch, would satisfy the positive one alone.
            check("...and NOT at the old flat assets-dir root",
                  not (root / ASSET_DIR / "s-agent.png").exists())
            check("the prompt library is in its own folder too",
                  (root / prompt_library.PROMPT_DIR / "prompts.json").is_file()
                  and not (root / ASSET_DIR / "prompts.json").exists())
            check("...and the indexes stayed at the root",
                  (root / ASSET_DIR / "manifest.json").is_file())
            check("...naming its source", out.get("source") == url)
            check("...and the manifest row", json.loads(
                (root / ASSET_DIR / "manifest.json").read_text())["assets"][-1]["surface"] == "s")
            lib = prompt_library.load(root)["prompts"]
            check("the ingest records the prompt too", len(lib) == 1)
            check("...with the model the agent stated", lib[0]["model"] == "seedream-4.5")
            check("...and the money it actually cost", lib[0]["spent_total_usd"] == 0.04)

            # THE FORMAT IS SNIFFED FROM THE FETCHED BYTES, through the CLI. A URL that serves PNG
            # for a `vector` row must be refused, not written to a `.svg` that lies about its
            # contents -- a raster named `.svg` does not scale and does not recolour from tokens,
            # which is the entire reason a vector was asked for.
            (root / ".design-flow/generation.json").write_text(json.dumps({
                "aggregator": "agent", "budget_usd": 1.0,
                "ladders": {"vector": [{"name": "agent", "cost_usd": 0.0}]},
                "briefs": {"v": {"style": "flat-vector", "subject": "a tray", "mood": "light",
                                 "palette": ["monochrome"]}},
            }), encoding="utf-8")
            (root / "vec.json").write_text(json.dumps({
                "kind": "vector", "pack": {"variant": "default"},
                "library_miss": {"searched_for": "a tray", "why_no_fit": "none"},
                "tier_refusal": {"surface": "v", "tier_1_why_not": "a", "tier_2_why_not": "b"}}),
                encoding="utf-8")
            proc = _sp.run([sys.executable, str(Path(__file__).resolve()), "--request", "vec.json",
                            "--from-url", url], cwd=root, capture_output=True, text=True, timeout=60)
            check(f"a URL serving the wrong format is refused (exit {proc.returncode})",
                  proc.returncode == 2)
            check("...before writing anything",
                  not (root / ASSET_LIBRARY / "v-agent.svg").exists())
        finally:
            srv.shutdown()

    # #629. THE CHAT-COMPLETIONS RASTER ADAPTER. Nothing here reaches the network -- the response is
    # stubbed, because a test that needed a provider would be a bill rather than a test. What is
    # asserted is the shape handling, which is where a wrong guess costs a billed call: the shape
    # was verified against OpenRouter's chat-completion reference before this was written.
    real_urlopen = urllib.request.urlopen
    try:
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

        class _R:
            def __init__(self, payload): self._b = json.dumps(payload).encode()
            def read(self, _n=None): return self._b
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def respond(payload):
            urllib.request.urlopen = lambda *a, **k: _R(payload)

        data_url = "data:image/png;base64," + base64.b64encode(png).decode()
        respond({"choices": [{"message": {"images": [{"image_url": {"url": data_url}}]}}],
                 "usage": {"cost": 0.068}})
        blob, cost = call_openrouter_chat_image("k", "m", "p", None, 5)
        check("the chat-image adapter decodes the data URL", blob == png)
        check("...and reports the REAL cost from usage", cost == 0.068)

        # A TEXT-ONLY REPLY IS NOT AN ASSET, and it is the likeliest failure: a model that does not
        # support the image modality answers in prose about the picture it would have drawn.
        # Saving that would put a paragraph in the manifest where art belongs.
        respond({"choices": [{"message": {"content": "I would draw a calm lattice."}}]})
        checks += 1
        try:
            call_openrouter_chat_image("k", "m", "p", None, 5)
            failures.append("a text-only reply should refuse, not be saved")
        except Unusable as exc:
            if "no image" not in str(exc) or "--discover" not in str(exc):
                failures.append(f"a text-only reply refused without naming the fix: {exc}")

        # A LINK RATHER THAN A DATA URL is a provider change, not a crash. Say which flag handles it
        # instead of guessing at a download inside an adapter that documents itself as base64-only.
        respond({"choices": [{"message": {"images": [
            {"image_url": {"url": "https://cdn.example/x.png"}}]}}]})
        checks += 1
        try:
            call_openrouter_chat_image("k", "m", "p", None, 5)
            failures.append("a non-data URL should refuse")
        except Unusable as exc:
            if "--from-url" not in str(exc):
                failures.append(f"a non-data URL refused without naming --from-url: {exc}")

        respond({"choices": [{"message": {"images": [
            {"image_url": {"url": "data:image/png;base64,"}}]}}]})
        checks += 1
        try:
            call_openrouter_chat_image("k", "m", "p", None, 5)
            failures.append("a data URL decoding to nothing should refuse")
        except Unusable as exc:
            if "decoded to nothing" not in str(exc):
                failures.append(f"an empty data URL refused for the wrong reason: {exc}")

        # A MISSING COST IS NULL, NOT ZERO. Recording an unreported charge as $0.00 would make the
        # budget approve against a number the provider never quoted.
        respond({"choices": [{"message": {"images": [{"image_url": {"url": data_url}}]}}]})
        _, cost = call_openrouter_chat_image("k", "m", "p", None, 5)
        check("an unreported cost is null, never zero", cost is None)

        # THE STYLE REFERENCE MUST REACH THE PROVIDER. `generate.md` §3e calls it "the single
        # biggest lever on consistency", and the first version of this adapter accepted the
        # parameter and dropped it -- so a project that had approved a reference got none of its
        # benefit and no warning. Nothing asserted it, which is why it shipped. Capture the request
        # body and look, rather than trusting the signature.
        sent: list[dict] = []

        def capture(req, *a, **k):
            sent.append(json.loads(req.data.decode()))
            return _R({"choices": [{"message": {"images": [{"image_url": {"url": data_url}}]}}]})

        urllib.request.urlopen = capture
        ref = b"\xff\xd8\xff" + b"\x00" * 32                    # a JPEG, deliberately not a PNG
        call_openrouter_chat_image("k", "m", "the prompt", ref, 5)
        content = sent[-1]["messages"][0]["content"]
        check("a style reference is SENT, not dropped", isinstance(content, list))
        # Read through a list-guard: with the reference dropped, `content` is a STRING, and
        # iterating it yields characters whose `.get` raises -- the run would die before printing
        # the failure above, and a crash is not a verdict. The mutation guard found this.
        parts = content if isinstance(content, list) else []
        check("...with the prompt still in it",
              any(p.get("text") == "the prompt" for p in parts))
        check("...and the image beside it",
              any(p.get("type") == "image_url" for p in parts))
        # DECLARED AS WHAT IT IS. Every adapter hardcoded `image/png`; a provider that validates the
        # declared type against the bytes rejects a JPEG labelled PNG, losing the reference exactly
        # when it was meant to be doing the most work.
        check("...declared with its REAL mime type, not a hardcoded png",
              any("data:image/jpeg;base64," in (p.get("image_url") or {}).get("url", "")
                  for p in parts))
        check("...and modalities still requested", sent[-1]["modalities"] == ["image", "text"])

        sent.clear()
        call_openrouter_chat_image("k", "m", "the prompt", None, 5)
        check("no reference means a plain string content, not an empty part list",
              sent[-1]["messages"][0]["content"] == "the prompt")

        # THE MIME IS SNIFFED, NEVER ASSUMED — inside the try, so the stubbed urlopen is restored
        # either way.
        for blob, want in ((b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"),
                           (b"RIFF____WEBP", "image/webp"),
                           (b"<svg viewBox='0 0 1 1'>", "image/svg+xml")):
            check(f"the reference mime sniffs {want}", reference_mime(blob) == want)
        check("...and an unknown blob falls back to png rather than raising",
              reference_mime(b"\x00\x01\x02\x03") == "image/png")
    finally:
        urllib.request.urlopen = real_urlopen

    # THE `video` KIND SNIFFS TOO. Reachable now that --from-url can feed any row from any URL, and
    # providers do serve a poster image at a video's URL.
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16
    check("real MP4 bytes are accepted as video", assert_kind_matches("video", mp4) == "mp4")
    checks += 1
    try:
        assert_kind_matches("video", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        failures.append("a still recorded as video should be refused")
    except Unusable as exc:
        if "thumbnail" not in str(exc):
            failures.append(f"a still-as-video refused without naming the likely cause: {exc}")
    check("...and a still is still fine as `static`",
          assert_kind_matches("static", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16) == "png")

    # #640. THE SHAPE READER. Header-only, stdlib, and it must return None rather than guess — a
    # fabricated dimension is worse than an absent one, because it would refuse a correct asset.
    # The PNG/JPEG/GIF branches were validated against real files produced by `sips` before these
    # synthetic fixtures were written; WebP is covered from the documented header layout only.
    def png(w: int, h: int) -> bytes:
        return (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR"
                + w.to_bytes(4, "big") + h.to_bytes(4, "big") + b"\x08\x06\x00\x00\x00")

    check("a PNG header gives its size", image_size(png(1024, 576)) == (1024, 576))
    check("a GIF header gives its size (LITTLE endian, unlike PNG)",
          image_size(b"GIF89a" + (800).to_bytes(2, "little") + (600).to_bytes(2, "little"))
          == (800, 600))
    check("an SVG viewBox gives the RATIO, which is what an aspect check wants",
          image_size(b'<svg viewBox="0 0 21 9"></svg>') == (21, 9))
    check("...falling back to px width/height when there is no viewBox",
          image_size(b'<svg width="800" height="600"></svg>') == (800, 600))
    # `width="8cm"` is a PHYSICAL size whose pixel ratio depends on the renderer. Treating 8 as
    # pixels would compare a centimetre against a pixel and refuse a correct asset.
    check("...and refusing to read a physical unit as pixels",
          image_size(b'<svg width="8cm" height="6cm"></svg>') is None)
    check("an unreadable blob measures None rather than guessing",
          image_size(b"\x00\x01\x02\x03") is None)

    print("the shape is checked against what the brief asked for")
    check("`16:9` parses", abs((parse_aspect("16:9") or 0) - 16 / 9) < 1e-9)
    check("...and `1:1`", parse_aspect("1:1") == 1.0)
    check("nonsense parses to None, never a guess", parse_aspect("wide-ish") is None)
    check("an exact match passes", assert_aspect(png(1024, 576), "16:9") is None)
    check("...and so does a hair off, inside the stated tolerance",
          assert_aspect(png(1024, 580), "16:9") is None)
    checks += 1
    try:
        assert_aspect(png(1024, 1024), "21:9")
        failures.append("a square delivered for a 21:9 band should be refused")
    except Unusable as exc:
        if "1024x1024" not in str(exc) or "tolerance" not in str(exc):
            failures.append(f"the aspect refusal should name the size and the tolerance: {exc}")
    # NOTHING ASKED, NOTHING CHECKED. A project that states no aspect must be unaffected, or this
    # lands as a breaking change on every asset rather than on the ones that asked for a shape.
    check("no stated aspect means no check at all", assert_aspect(png(3, 7), None) is None)
    # UNREADABLE DIMENSIONS PASS: refusing there would turn "we could not measure" into "the
    # provider was wrong", blocking a correct asset over our own gap.
    check("an unmeasurable blob passes rather than being accused",
          assert_aspect(b"\x00\x01\x02\x03", "16:9") is None)

    print("a motion asset must actually move")
    checks += 1
    try:
        assert_kind_matches("motion", b"<svg viewBox='0 0 10 10'><path d='M0 0h10'/></svg>")
        failures.append("a static SVG recorded as motion should be refused")
    except Unusable as exc:
        if "no animation" not in str(exc):
            failures.append(f"a static SVG refused for the wrong reason: {exc}")
    check("...but SMIL is accepted",
          assert_kind_matches("motion", b"<svg><animate attributeName='x' dur='1s'/></svg>") == "svg")
    # A `<style>` block with @keyframes is how a TOKEN-RECOLOURED animated SVG is normally authored,
    # so checking only for SMIL would refuse the idiom our own doctrine points at.
    check("...and so is a @keyframes stylesheet, the token-recolourable idiom",
          assert_kind_matches("motion", b"<svg><style>@keyframes d{}</style></svg>") == "svg")
    checks += 1
    try:
        assert_kind_matches("motion", b'{"nothing": true}')
        failures.append("arbitrary JSON recorded as motion should be refused")
    except Unusable as exc:
        if "not a Lottie" not in str(exc):
            failures.append(f"non-Lottie JSON refused for the wrong reason: {exc}")
    check("...but a real Lottie shape is accepted",
          assert_kind_matches("motion", b'{"v":"5.7.4","fr":30,"op":60,"layers":[]}') == "json")

    check("the chat-image adapter is registered", "openrouter-chat-image" in ADAPTERS)
    check("...and did not displace the images-endpoint one", "openrouter" in ADAPTERS)
    check("...and it needs a key, unlike the roles",
          "openrouter-chat-image" not in KEYLESS)

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} generate-asset assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
