"""Mutation guard: generate_asset. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="generate_asset",
    subject="plugins/design-flow/scripts/generate_asset.py",
    selftest="plugins/design-flow/scripts/generate_asset.py",   # --selftest lives in the module
    # `needs` the sibling it imports. Without it the staged mutant cannot import
    # generation_gate, the selftest dies on ModuleNotFoundError, and every mutation reads as
    # "caught" while proving nothing -- a crash is not a verdict, and this guard demonstrated it.
    # #625 added the second import, and the rule is the one above rather than a new one: a
    # guard's `needs` is EVERYTHING the subject opens, so an added import is an added need.
    needs=("plugins/design-flow/scripts/generation_gate.py",
           "plugins/design-flow/scripts/prompt_library.py"),
    # Every fixture is a tempdir and NOTHING reaches the network. A test that needed
    # a provider would not be a test -- it would be a bill. Each mutation removes one thing that
    # stands between a request and someone's card.
    mutations=(
        Mutation(
            # A still recorded as footage renders a frozen frame where motion was planned, and
            # providers really do serve a poster image at a video's URL. Reachable since
            # --from-url let any URL feed any row.
            "a still image is accepted as video, so a poster frame records as footage",
            '    if kind == "video" and ext not in ("mp4", "webm"):',
            "    if False:",
            "a still recorded as video should be refused",
        ),
        Mutation(
            # #640. A square delivered for a wide band is cropped at composition time, throwing
            # away the part of the picture that was paid for -- and the row still says `done`.
            "the returned shape is never checked against the aspect the brief asked for",
            "    if abs(got - want) / want > ASPECT_TOLERANCE:",
            "    if False:",
            "a square delivered for a 21:9 band should be refused",
        ),
        Mutation(
            # #641. The `motion` kind checked only the extension, which the animated and the
            # static case share. A static drawing recorded as motion is a `done` row whose
            # surface animates nothing.
            "a static SVG passes as a motion asset again",
            '                    and "@keyframes" not in text and not re.search(r"\\banimation\\s*:", text):',
            "                    and False:",
            "a static SVG recorded as motion should be refused",
        ),
        Mutation(
            # Any JSON at all used to pass as a Lottie. Checking the SHAPE rather than merely
            # "is JSON" is the whole point.
            "any JSON passes as a Lottie animation",
            '            missing = [k for k in ("v", "fr", "op", "layers") if k not in doc]',
            "            missing = []",
            "arbitrary JSON recorded as motion should be refused",
        ),
        Mutation(
            # The style reference is "the single biggest lever on consistency" (generate.md
            # §3c), and the first version of this adapter accepted the parameter and DROPPED it.
            # Nothing asserted it, so it shipped: a project that had approved a reference got
            # none of its benefit and no warning either.
            "the style reference is silently dropped, so on-brand consistency is not requested",
            "    content: list[dict] | str = prompt\n    if reference:",
            "    content: list[dict] | str = prompt\n    if False:",
            "a style reference is SENT, not dropped",
        ),
        Mutation(
            # Hardcoding image/png is a lie the moment a project points style_reference at a
            # .jpg, and a provider that validates the declared type rejects the call -- losing
            # the reference exactly when it was meant to be doing the most work.
            "the reference mime is hardcoded again, so a JPEG is declared a PNG",
            '    ext = sniff_extension(blob)\n    return {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp",\n            "svg": "image/svg+xml"}.get(ext, "image/png")',
            '    return "image/png"',
            "the reference mime sniffs image/jpeg",
        ),
        Mutation(
            # #629. A model without the image modality answers in PROSE about the picture it
            # would have drawn. Saved, that is a paragraph in the manifest where art belongs --
            # and it looks like a completed row.
            "a text-only reply is saved as though it were an image",
            "    if not images:",
            "    if False:",
            # Matched on the fixture NAME, not one branch's message: with the guard
            # removed the reply is still refused, just by the data-URL check and
            # without naming the fix, so the fixture reports a different sentence.
            "a text-only reply",
        ),
        Mutation(
            # An unreported charge recorded as $0.00 makes the budget approve against a number
            # the provider never quoted -- the same defect as an unpriced ladder rung.
            "a missing provider cost is recorded as zero rather than unknown",
            '    cost = (payload.get("usage") or {}).get("cost")\n'
            "    return blob, (float(cost) if cost is not None else None)",
            '    cost = (payload.get("usage") or {}).get("cost")\n'
            "    return blob, float(cost or 0.0)",
            "an unreported cost is null, never zero",
        ),
        Mutation(
            # #628. `--from-url` takes a string an agent read out of a tool result, so the
            # scheme check is the only thing between that string and `urlopen` reading this
            # machine. A `file:` URL would be fetched, sniffed, written into docs/assets and
            # committed as though a model had made it -- a local secret laundered into art.
            "any URL scheme is fetched, so file: reads this machine into the asset folder",
            '    if scheme not in ("http", "https"):',
            "    if False:",
            "only http(s) is fetched",
        ),
        Mutation(
            # A 0-byte download recorded as an asset is a `done` row nobody can see. The row
            # says finished, the manifest says present, and the surface renders nothing.
            "an empty download is recorded, so a 0-byte file enters the manifest as art",
            # Multi-line anchor: `if not blob:` alone matches the chat-image adapter too,
            # and an ambiguous anchor is a mutation that silently moves to another check.
            '    if not blob:\n        raise Unusable(f"{url} returned no bytes.',
            '    if False:\n        raise Unusable(f"{url} returned no bytes.',
            "an empty download should be refused",
        ),
        Mutation(
            # A raster written to `.svg` opens, looks plausible in a listing, and is the wrong
            # format -- it does not scale and does not recolour from tokens, which is the whole
            # reason a vector was asked for. Sniffing the FETCHED bytes is what stops it.
            "the ingest trusts the row's kind instead of the bytes it just downloaded",
            '            ext = assert_kind_matches(prov.get("kind", "static"), blob)',
            '            ext = "png"',
            "a URL serving the wrong format is refused",
        ),
        Mutation(
            # #625. The prompt is what makes a bought asset reproducible, and the reject path is
            # the half most easily dropped: recording only the keepers leaves the next run
            # unable to see that this prompt was already tried and disliked, so it pays for the
            # same disappointment again. Nothing else in the flow would notice.
            "a rejected prompt is not recorded, so the next run re-buys the disappointment",
            '    warning = remember_prompt(root, config, prov, approval["prompt"], asset=None, model=None,\n'
            '                              verdict="reject", why=why)',
            "    warning = None",
            "reject records the prompt",
        ),
        Mutation(
            # A critic with no criterion produces an OPINION, and an opinion recorded as a
            # verdict is worse than no verdict -- it looks like the check ran.
            "a surface with no acceptance check is still critiqued, so opinion becomes verdict",
            "    if not criterion:",
            "    if False:",
            "a surface with no acceptance check should refuse to be critiqued",
        ),
        Mutation(
            # A verdict nobody can review (accept) or act on (reject) is not a verdict.
            "a verdict needs no reason, so accepts cannot be reviewed and rejects not acted on",
            "    if not why.strip():",
            "    if False:",
            "verdict with no reason should be refused",
        ),
        Mutation(
            # The agent path never calls an API. Demanding a key from it refused the one
            # zero-cost route for a credential it had no use for -- which is what shipped until
            # the adapter was resolved before the preflight.
            "the agent path demands an API key it never uses",
            '    key = "" if name in KEYLESS else preflight_key(config.get("api_key_env", ""), root)',
            '    key = preflight_key(config.get("api_key_env", ""), root)',
            "the agent path needs no API key (refused instead",
        ),
        Mutation(
            # An agent-authored asset must get NO easier route into the manifest than a bought
            # one, or "the agent wrote it" becomes the way past every refusal.
            "a raster recorded as vector is accepted, so `.svg` stops meaning vector",
            '    if kind == "vector" and ext != "svg":',
            "    if False:",
            "a raster recorded as vector is still refused",
        ),
        Mutation(
            # Two shipped messages promised `.env` worked while nothing read the file, so a
            # user who followed the instruction got "not set" and concluded the tool was broken.
            "the .env fallback goes, so a promised location silently stops working",
            "    if raw is None and root is not None:",
            "    if False:",
            "a key in .env is found",
        ),
        Mutation(
            # A shell export is the more deliberate act. If a stale file could override it,
            # someone debugging a key would be overridden by something they had forgotten.
            "the environment stops winning, so a stale .env overrides a deliberate export",
            "    if raw is None and root is not None:",
            "    if root is not None:",
            "the environment beats .env",
        ),
        Mutation(
            # The load-bearing property: the gate is RE-RUN here, never trusted from the caller.
            # Drop it and a hand-written {"approved": true} bypasses every refusal at once --
            # library, tier precondition, composed prompt, budget ceiling.
            "the gate stops being re-run, so a forged approval reaches the provider",
            "    approval = decide(root, request)  # produce(): RE-RUN, never trusted from the caller",
            '    approval = request if request.get("approved") else decide(root, request)',
            "expected a Refusal, got Unusable",
        ),
        Mutation(
            # A placeholder key calls the provider and fails there with an error that reads like
            # an outage, sending someone to debug the wrong system.
            "a placeholder key is treated as real, so the call fails at the provider",
            '    if PLACEHOLDER_RE.match((raw or "").strip()):',
            "    if False:",
            "should be rejected as a placeholder",
        ),
        Mutation(
            "an absent key stops being caught, so the default install walks into the call",
            "    if raw is None:",
            "    if False:",
            "an absent key is distinguished from a placeholder",
        ),
        Mutation(
            # A manifest that grows unusable rows is worse than one that refuses to grow: the
            # asset looks findable and still gets re-generated by whoever could not tell.
            "incomplete manifest rows are written, so the library grows rows nobody can act on",
            # Multi-line anchor: #641 added a second `if missing:` in the Lottie shape
            # check, and an ambiguous anchor silently moves to a different rule.
            '    if missing:\n        raise Unusable(f"refusing to write a manifest row missing',
            '    if False:\n        raise Unusable(f"refusing to write a manifest row missing',
            "a row missing file should be refused",
        ),
    ),
)
