#!/usr/bin/env python3
"""The release image build: `docker build` with the build args and labels the project declares (#1701).

`/pipeline:release` used to run a bare `docker build -t IMAGE:SHA -t IMAGE:latest .`, so an app that reads its
version from a build arg, or a Kamal deploy that needs a `service` label, got an image that silently lacked
both. A project now declares them in `pipeline.yml`:

    build_args: { APP_VERSION: "{{release_name}}" }
    labels:     { service: myapp }

* Each `build_args` entry becomes `--build-arg NAME=VALUE`, each `labels` entry `--label KEY=VALUE`.
  `{{sha}}` (the short certified sha) and `{{release_name}}` are interpolated in the values; nothing else is,
  and an unknown `{{name}}` is an error rather than text that reaches an image label.
* `{{release_name}}` is `--release-name`, else `$RELEASE_NAME`, else the sha.
* With neither key set the command is EXACTLY the old one.
* The argv is a list handed to `docker` with no shell, so a value with spaces, quotes or `$(...)` stays one
  argument and is never evaluated.
* The report prints every build arg and label it passed (values included: build args are visible in the image's
  history, so a secret does not belong in one) and names every Dockerfile `ARG` that has no default anywhere
  and that the config does not feed. It names them and does not block: some ARGs are meant to stay unset, and
  the person reading the report decides. Docker's own predefined args (proxy and platform) are never named:
  https://docs.docker.com/build/building/variables/ .
* The two keys are read strictly (a flat mapping of strings, flow `{ A: b }` or block form). A shape this reader
  does not understand is exit 2 with the line, never a silent skip: a build that silently drops its version
  arg is the defect this script exists to end.

Exit: 0 built (or `--dry-run` printed), 2 the config or the arguments are unusable, else docker's own code.
"""
import argparse
import os
import re
import shlex
import subprocess
import sys
import tempfile

# https://docs.docker.com/build/building/variables/ (checked 2026-10-10): the proxy args (case-insensitive) and
# the platform args are supplied by Docker without a `--build-arg`.
PREDEFINED = {
    "http_proxy", "https_proxy", "ftp_proxy", "no_proxy", "all_proxy",
    "buildplatform", "buildos", "buildarch", "buildvariant",
    "targetplatform", "targetos", "targetarch", "targetvariant",
}
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LABEL_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
VAR = re.compile(r"\{\{([^{}]*)\}\}")
KEYS = ("build_args", "labels")


class ConfigError(Exception):
    pass


def _strip_comment(line):
    """Drop a trailing `# comment` that is not inside quotes."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    return line


def _unquote(text, where):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text[:1] in "\"'" or text[-1:] in "\"'":
        raise ConfigError(f"{where}: an unbalanced quote in {text!r}")
    return text


def _pairs_from_flow(body, where):
    """`A: b, C: "d, e"` (the inside of `{ ... }`) as (key, value) pairs; a comma inside quotes stays."""
    items, current, quote = [], "", None
    for ch in body:
        if quote:
            quote = None if ch == quote else quote
            current += ch
        elif ch in "\"'":
            quote = ch
            current += ch
        elif ch == ",":
            items.append(current)
            current = ""
        else:
            current += ch
    if quote:
        raise ConfigError(f"{where}: an unbalanced quote in {body!r}")
    items.append(current)
    pairs = []
    for item in items:
        if not item.strip():
            continue
        if ":" not in item:
            raise ConfigError(f"{where}: {item.strip()!r} is not `key: value`")
        key, value = item.split(":", 1)
        pairs.append((_unquote(key, where), _unquote(value, where)))
    return pairs


def read_config(text):
    """{'build_args': {...}, 'labels': {...}} from pipeline.yml's text; only these two keys are read."""
    found = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = _strip_comment(lines[i])
        match = re.match(r"^(build_args|labels)\s*:(.*)$", raw)
        i += 1
        if not match:
            continue
        key, rest = match.group(1), match.group(2).strip()
        where = f"pipeline.yml `{key}`"
        if key in found:
            raise ConfigError(f"{where}: declared twice")
        if rest:
            if not (rest.startswith("{") and rest.endswith("}")):
                raise ConfigError(f"{where}: write a mapping, `{{ NAME: value }}` or an indented block; got {rest!r}")
            pairs = _pairs_from_flow(rest[1:-1], where)
        else:
            pairs = []
            while i < len(lines):
                nxt = _strip_comment(lines[i])
                if not nxt.strip():
                    i += 1
                    continue
                if not nxt.startswith((" ", "\t")):
                    break
                if ":" not in nxt:
                    raise ConfigError(f"{where}: {nxt.strip()!r} is not `key: value`")
                k, v = nxt.split(":", 1)
                pairs.append((_unquote(k, where), _unquote(v, where)))
                i += 1
        mapping = {}
        for k, v in pairs:
            if (NAME if key == "build_args" else LABEL_KEY).match(k) is None:
                raise ConfigError(f"{where}: {k!r} is not a valid {'build arg name' if key == 'build_args' else 'label key'}")
            if k in mapping:
                raise ConfigError(f"{where}: {k} is declared twice")
            mapping[k] = v
        found[key] = mapping
    return {key: found.get(key, {}) for key in KEYS}


def interpolate(value, variables, where):
    def sub(match):
        name = match.group(1)
        if name not in variables:
            raise ConfigError(f"{where}: unknown {{{{{name}}}}}; the variables are {', '.join('{{' + v + '}}' for v in sorted(variables))}")
        return variables[name]
    return VAR.sub(sub, value)  # exactly `{{sha}}` / `{{release_name}}`: `{{ sha }}` is unknown, and an error, not text


def build_argv(image, sha, config, release_name, context="."):
    """The `docker build` argument list. With no keys declared it is the old bare command."""
    variables = {"sha": sha, "release_name": release_name}
    args = {k: interpolate(v, variables, f"build_args.{k}") for k, v in config["build_args"].items()}
    labels = {k: interpolate(v, variables, f"labels.{k}") for k, v in config["labels"].items()}
    argv = ["docker", "build"]
    for name, value in args.items():
        argv += ["--build-arg", f"{name}={value}"]
    for key, value in labels.items():
        argv += ["--label", f"{key}={value}"]
    argv += ["-t", f"{image}:{sha}", "-t", f"{image}:latest", context]
    return argv, args, labels


def dockerfile_args(text):
    """(names with a default somewhere, names with none anywhere) over every ARG in the Dockerfile.

    A stage's bare `ARG X` inherits a global `ARG X=1`, so a name counts as defaulted when ANY declaration of
    it has a default."""
    joined = re.sub(r"\\\s*\n", " ", text)
    with_default, seen = set(), []
    for line in joined.splitlines():
        match = re.match(r"^\s*ARG\s+(.+)$", _strip_comment(line), re.IGNORECASE)
        if not match:
            continue
        for token in shlex.split(match.group(1), posix=True):
            name, has = (token.split("=", 1)[0], "=" in token)
            seen.append(name)
            if has:
                with_default.add(name)
    unfed = [n for n in dict.fromkeys(seen) if n not in with_default]
    return with_default, unfed


def unfed_args(dockerfile_text, fed):
    _, none = dockerfile_args(dockerfile_text)
    return [n for n in none if n not in fed and n.lower() not in PREDEFINED]


def report(argv, args, labels, unfed, scanned):
    lines = ["release build:", "  " + shlex.join(argv)]
    lines.append("  build args passed: " + (", ".join(f"{k}={v}" for k, v in args.items()) or "none"))
    lines.append("  labels passed: " + (", ".join(f"{k}={v}" for k, v in labels.items()) or "none"))
    if not scanned:
        lines.append("  Dockerfile: not found, ARGs not scanned")
    elif unfed:
        lines.append("  UNFED ARG (no default, not in build_args): " + ", ".join(unfed)
                     + " -- the image is built without a value for each; declare it under `build_args` in pipeline.yml, or ignore it if it is meant to stay unset")
    else:
        lines.append("  Dockerfile ARGs: every ARG without a default is fed")
    return "\n".join(lines)


def run(image, sha, release_name, config_path, dockerfile, context, dry_run, runner=subprocess.run, out=print):
    try:
        text = open(config_path, encoding="utf-8").read() if os.path.exists(config_path) else ""
        config = read_config(text)
        name = release_name or os.environ.get("RELEASE_NAME") or sha
        argv, args, labels = build_argv(image, sha, config, name, context)
    except ConfigError as error:
        out(f"release build: {error}")
        return 2
    scanned = os.path.exists(dockerfile)
    unfed = unfed_args(open(dockerfile, encoding="utf-8").read(), set(args)) if scanned else []
    out(report(argv, args, labels, unfed, scanned))
    if dry_run:
        return 0
    return runner(argv).returncode


def selftest():
    failures = []

    def check(label, ok, detail=""):
        if not ok:
            failures.append(f"{label}: {detail}")

    def raises(text):
        try:
            read_config(text)
        except ConfigError:
            return True
        return False

    base = ["docker", "build", "-t", "img:abc1234", "-t", "img:latest", "."]
    # no keys: exactly the old command (acceptance 4)
    argv, _, _ = build_argv("img", "abc1234", read_config("mode: local\n"), "abc1234")
    check("no keys is the bare command", argv == base, argv)
    argv, _, _ = build_argv("img", "abc1234", read_config(""), "abc1234")
    check("an empty config is the bare command", argv == base, argv)
    # flow and block forms read the same
    flow = read_config('build_args: { APP_VERSION: "{{release_name}}", B: x }\nlabels: { service: app }\n')
    block = read_config('mode: local\nbuild_args:\n  APP_VERSION: "{{release_name}}"  # the version\n  B: x\nlabels:\n  service: app\nimage: y\n')
    check("flow and block agree", flow == block, (flow, block))
    check("flow content", flow == {"build_args": {"APP_VERSION": "{{release_name}}", "B": "x"}, "labels": {"service": "app"}}, flow)
    check("a comma inside quotes stays", read_config('labels: { a: "x, y", b: z }')["labels"] == {"a": "x, y", "b": "z"})
    check("an empty mapping is no key", read_config("build_args: {}\n")["build_args"] == {})
    check("a commented-out key is not read", read_config("# build_args: { A: b }\n")["build_args"] == {})
    # unreadable shapes are errors, never skips
    for label, text in (("a scalar", "build_args: APP\n"), ("a list", "build_args: [A=1]\n"), ("a bad name", "build_args: { 1A: x }\n"),
                        ("a twice-declared key", "build_args: { A: 1 }\nbuild_args: { B: 2 }\n"), ("a twice-declared name", "build_args: { A: 1, A: 2 }\n"),
                        ("a block line without a colon", "labels:\n  service\n"), ("an unbalanced quote", 'labels: { a: "x }\n'),
                        ("a bad label key", "labels: { -a: x }\n")):
        check(f"{label} is an error", raises(text))
    # interpolation and its precedence
    cfg = {"build_args": {"APP_VERSION": "{{release_name}}", "SHA": "{{sha}}"}, "labels": {"service": "app"}}
    argv, args, labels = build_argv("img", "abc1234", cfg, "v1.3.0")
    check("args and labels are passed", argv == ["docker", "build", "--build-arg", "APP_VERSION=v1.3.0", "--build-arg", "SHA=abc1234",
                                                  "--label", "service=app", "-t", "img:abc1234", "-t", "img:latest", "."], argv)
    check("the dicts are what was passed", (args, labels) == ({"APP_VERSION": "v1.3.0", "SHA": "abc1234"}, {"service": "app"}))
    for bad in ("{{nope}}", "{{ sha }}", "{{}}"):
        try:
            build_argv("img", "abc1234", {"build_args": {"A": bad}, "labels": {}}, "n")
            check(f"{bad} is an error", False)
        except ConfigError as error:
            check(f"{bad} is named", bad in str(error), str(error))
    # a value is one argument, never evaluated (no shell)
    nasty = 'a b"c$(touch x)\'d'
    argv, _, _ = build_argv("img", "abc1234", {"build_args": {"X": nasty}, "labels": {}}, "n")
    check("a hostile value stays one argv element", argv[3] == f"X={nasty}" and len(argv) == len(base) + 2, argv)
    # the Dockerfile scan
    docker = ('ARG RUBY_VERSION=3.4\nFROM ruby:$RUBY_VERSION AS base\nARG APP_VERSION\nARG TARGETARCH\nARG http_proxy\n'
              'ARG A=1 B\nARG RUBY_VERSION\n# ARG COMMENTED\nARG MULTI \\\n  =x\nARG  \\\n  CONT\nARG TARGETARCHX\nARG NO_PROXY_EXTRA\n')
    names = unfed_args(docker, set())
    check("an unfed ARG is named", "APP_VERSION" in names, names)
    check("predefined args are never named", not ({"TARGETARCH", "http_proxy"} & set(names)), names)
    check("a near-miss of a predefined name is named", {"TARGETARCHX", "NO_PROXY_EXTRA"} <= set(names), names)
    check("a name with a default anywhere is not unfed", not ({"RUBY_VERSION", "A"} & set(names)), names)
    check("a bare ARG beside a defaulted one is named", "B" in names, names)
    check("a commented ARG is not read", "COMMENTED" not in names, names)
    check("a continued declaration is read", "CONT" in names, names)
    check("a fed ARG is not named", "APP_VERSION" not in unfed_args(docker, {"APP_VERSION"}))
    check("the report says unfed loudly", "UNFED ARG" in report(base, {}, {}, ["X"], True))
    check("the report says nothing is unfed when so", "every ARG without a default is fed" in report(base, {}, {}, [], True))
    check("the report prints what it passed", "APP_VERSION=v1" in report(base, {"APP_VERSION": "v1"}, {"s": "a"}, [], True)
          and "s=a" in report(base, {"APP_VERSION": "v1"}, {"s": "a"}, [], True))
    # run(): dry-run builds nothing, a real run calls the runner once and returns its code, errors are 2
    with tempfile.TemporaryDirectory() as tmp:
        cfgp, dfp = os.path.join(tmp, "pipeline.yml"), os.path.join(tmp, "Dockerfile")
        open(cfgp, "w").write('build_args: { APP_VERSION: "{{release_name}}" }\n')
        open(dfp, "w").write("FROM scratch\nARG APP_VERSION\nARG OTHER\n")
        out, calls = [], []

        def fake(argv):
            calls.append(argv)
            return type("R", (), {"returncode": 7})()

        check("dry-run exits 0", run("img", "abc1234", "v2", cfgp, dfp, ".", True, fake, out.append) == 0)
        check("dry-run runs nothing", calls == [], calls)
        check("dry-run names the unfed one only", "UNFED ARG (no default, not in build_args): OTHER" in out[0] and "APP_VERSION," not in out[0], out)
        out.clear()
        check("a real run returns docker's code", run("img", "abc1234", "v2", cfgp, dfp, ".", False, fake, out.append) == 7)
        check("a real run calls docker once with the arg", len(calls) == 1 and "APP_VERSION=v2" in calls[0], calls)
        os.environ.pop("RELEASE_NAME", None)
        out.clear()
        run("img", "abc1234", None, cfgp, dfp, ".", True, fake, out.append)
        check("the release name defaults to the sha", "APP_VERSION=abc1234" in out[0], out)
        os.environ["RELEASE_NAME"] = "v9"
        out.clear()
        run("img", "abc1234", None, cfgp, dfp, ".", True, fake, out.append)
        check("RELEASE_NAME beats the sha", "APP_VERSION=v9" in out[0], out)
        out.clear()
        run("img", "abc1234", "v3", cfgp, dfp, ".", True, fake, out.append)
        check("the flag beats RELEASE_NAME", "APP_VERSION=v3" in out[0], out)
        os.environ.pop("RELEASE_NAME", None)
        open(cfgp, "w").write("build_args: APP\n")
        out.clear()
        check("a bad config is exit 2 and builds nothing", run("img", "abc1234", "v", cfgp, dfp, ".", False, fake, out.append) == 2 and len(calls) == 1, out)
        out.clear()
        check("no config and no keys is the bare build", run("img", "abc1234", "v", os.path.join(tmp, "none.yml"), os.path.join(tmp, "none"), ".", True, fake, out.append) == 0
              and out[0].splitlines()[1].strip() == shlex.join(base), out)
    if failures:
        print("release_build selftest FAILED:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("release_build selftest passed")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the release image with the build args and labels pipeline.yml declares (#1701).")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--image")
    parser.add_argument("--sha")
    parser.add_argument("--release-name")
    parser.add_argument("--config", default="pipeline.yml")
    parser.add_argument("--dockerfile", default="Dockerfile")
    parser.add_argument("--context", default=".")
    parser.add_argument("--dry-run", action="store_true", help="print the command and the report; build nothing")
    ns = parser.parse_args(argv)
    if ns.selftest:
        return selftest()
    if not ns.image or not ns.sha:
        parser.error("--image and --sha are required")
    return run(ns.image, ns.sha, ns.release_name, ns.config, ns.dockerfile, ns.context, ns.dry_run)


if __name__ == "__main__":
    sys.exit(main())
