"""Mutation guard: check_security_review (#2119). Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_security_review",
    subject="scripts/check_security_review.py",
    selftest="scripts/check_security_review.py",
    selftest_args=("--selftest",),
    needs=("scripts/check_threat_model.py", "scripts/classify_door.py", "scripts/risky_diff.py"),
    mutations=(
        Mutation(
            "a record for an earlier commit stops being refused",
            '    if kind in ("missing", "no-head", "stale", "no-verdict"):',
            '    if kind in ("missing", "no-head", "no-verdict"):',
            "a record for another commit is stale",
        ),
        Mutation(
            "a mitigate row answered `not implemented` stops being BLOCKING",
            '            if verdict == "not implemented":',
            "            if False:",
            "a mitigate row not implemented is BLOCKING, exit 3",
        ),
        Mutation(
            "evidence past the end of the file is accepted",
            "                elif int(ev.group(2)) < 1 or int(ev.group(2)) > len(src):",
            "                elif int(ev.group(2)) < 1 or int(ev.group(2)) > 10**9:",
            "evidence past the end of the file is incomplete",
        ),
        Mutation(
            "a stale accept row stops being a finding",
            '            if verdict == "stale":',
            "            if False:",
            "a stale accept row is a finding, exit 3",
        ),
        Mutation(
            "a row the record leaves out stops being incomplete",
            '        if got is None:\n            incomplete.append(f"{label}: no answer in the record")\n            continue',
            "        if got is None:\n            continue",
            "a mitigate row with no answer is incomplete",
        ),
        Mutation(
            "a record that answers a row the model lacks is accepted",
            "    for n in sorted(set(answers) - known):",
            "    for n in []:",
            "a row the model does not have is another model",
        ),
        Mutation(
            "a model with no readable table stops being exit 2",
            "    if not threat_rows(model_text):",
            "    if False:",
            "an unreadable model is exit 2",
        ),
        Mutation(
            "a comment, blank or block-comment line is accepted as the line that implements a control",
            "                elif int(ev.group(2)) in non_code_lines(src):",
            "                elif False:",
            "evidence on a comment line is incomplete",
        ),
        Mutation(
            "a line inside =begin/=end counts as code",
            '            begin = not raw.startswith("=end")',
            "            begin = True",
            "evidence on code after a block comment passes",
        ),
        Mutation(
            "a heredoc body counts as code",
            "            heredocs = [m.group(2) for m in HEREDOC_RE.finditer(raw)]",
            "            heredocs = []",
            "evidence inside a heredoc body is incomplete",
        ),
        Mutation(
            "only the first of several heredocs on one line is tracked",
            "            heredocs = [m.group(2) for m in HEREDOC_RE.finditer(raw)]",
            "            heredocs = [m.group(2) for m in HEREDOC_RE.finditer(raw)][:1]",
            "evidence in the second of two heredocs opened on one line is incomplete",
        ),
        Mutation(
            "a committed symlink is read through, so its target path reads as code",
            '    if tree.returncode != 0 or not tree.stdout.strip() or tree.stdout.split()[0] == "120000":',
            "    if tree.returncode != 0 or not tree.stdout.strip():",
            "a committed symlink is refused, never read through its target",
        ),
        Mutation(
            "the middle of a /* */ span counts as code",
            "        if block:\n            out.add(n)\n            block = \"*/\" not in raw\n            continue",
            "        if False:\n            out.add(n)\n            block = \"*/\" not in raw\n            continue",
            "evidence in the middle of a /* */ span with no leading star is incomplete",
        ),
        Mutation(
            "an evidence path with `..` is normalised into the repository instead of refused",
            '    if p.is_absolute() or ".." in p.parts:\n        return None\n    tree = subprocess.run(',
            '    import os\n\n    p = PurePosixPath(os.path.normpath(p.as_posix()))\n    tree = subprocess.run(',
            "a `..` evidence path is refused",
        ),
        Mutation(
            "the evidence file is read from the working tree, not HEAD",
            '    if tree.returncode != 0 or not tree.stdout.strip() or tree.stdout.split()[0] == "120000":\n        return None  # not in HEAD, or a symlink: `git show` of a link prints its target path, which would read as code\n    proc = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{p.as_posix()}"], capture_output=True)',
            '    proc = type("P", (), {"returncode": 0 if (root / p).is_file() else 1, "stdout": (root / p).read_bytes() if (root / p).is_file() else b""})()',
            "evidence in a file that exists only in the working tree is refused",
        ),
    ),
)
