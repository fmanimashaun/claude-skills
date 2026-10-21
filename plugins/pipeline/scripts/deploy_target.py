#!/usr/bin/env python3
"""Which deploy target does this project's stack declare, and which agent runs it? (#2179, slice of #2162, decision 3)

Run:  python3 deploy_target.py [PROJECT]       # JSON: the stacks, the target, the artifact, the agent; exit 0
      python3 deploy_target.py --selftest

WHY THIS EXISTS. `/pipeline:deploy-cloud` was one stack's deploy command: it named that stack's host tool, its briefing
sheet and its credentials, and delegated to one hard-coded agent. That stack-only part now lives in the stack's own plugin (an
agent it declares), and `pipeline` keeps the neutral lifecycle. What decides which agent runs is the stack DESCRIPTOR
(`descriptor.deploy`, declared by a stack plugin in its `stacks.json`: `target`, `artifact`, `agent`), so a second stack's deploy
agent is a new descriptor in its own plugin, and nothing here changes.

THE DETECTOR IS A MIRRORED COPY. `detect_stack.py` in this directory is byte-identical to the canonical `detect_stack.py`
(the flow plugin's) and `scripts/lint_self_consistency.py` refuses a copy that drifts (rule `detect-stack-drift` names the pair). A plugin installs alone
and cannot import another's code, and this is the one place pipeline needs the detector's answer. It is imported, not re-implemented:
the sibling-plugin discovery is the detector's own, called once.

EXIT CODES, and what each means to the command that calls this:
  0  a stack was detected and declares a deploy target: the JSON names the agent to delegate to.
  1  there is nothing to deploy with: no stack was detected, or the detected stack declares no `deploy` in its descriptor. STOP.
  2  it cannot judge: a manifest or descriptor is unreadable or wrong, two stacks both declare a deploy target, or the agent a
     descriptor names does not exist. STOP and quote the printed problems.
  NEVER A DEFAULT. No target is the answer when the answer is unknown: 1 and 2 print why and name no agent, and the command stops.

Stdlib only, no network.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import detect_stack as ds  # noqa: E402  (the mirrored copy beside this file)


def target(project: Path, dirs: list[Path] | None = None, roots: list[Path] | None = None) -> tuple[int, dict]:
    """`(exit code, report)`. The report has `problems` (why it stopped) and, on exit 0, `target`, `artifact`, `agent` and `stacks`."""
    dirs = dirs if dirs is not None else ds.manifest_dirs(Path(ds.__file__))
    roots = roots if roots is not None else ds.agent_roots(Path(ds.__file__))
    code, report = ds.run(project, dirs, None, roots)
    stacks = [{"id": s["id"], "plugin": s["plugin"]} for s in report["stacks"]]
    if code == 2:
        return 2, {"stacks": stacks, "problems": report["problems"]}
    if code == 1:
        return 1, {"stacks": [], "problems": [f"no stack was detected in {project}: there is no deploy target to choose, and none is assumed"]}
    deploy = (report["descriptor"] or {}).get("deploy")
    ids = ", ".join(s["id"] for s in stacks)
    if not isinstance(deploy, dict) or not deploy.get("agent"):
        return 1, {"stacks": stacks, "problems": [f"the detected stack ({ids}) declares no `deploy` agent in its descriptor: there is nothing to deploy with"]}
    return 0, {"stacks": stacks, "target": deploy.get("target", ""), "artifact": deploy.get("artifact", ""), "agent": deploy["agent"],
               "problems": []}


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    if len(argv) > 1 or (argv and argv[0].startswith("-")):
        print(__doc__.splitlines()[0] + "\nusage: deploy_target.py [PROJECT] | --selftest", file=sys.stderr)
        return 2
    code, report = target(Path(argv[0] if argv else ".").resolve())
    if code == 0:
        print(json.dumps(report, indent=2))
    else:
        print(("STOP: cannot judge the deploy target" if code == 2 else "STOP: no deploy target") + "; no default is used:")
        for problem in report["problems"]:
            print(f"  - {problem}")
    return code


# ---------------------------------------------------------------------------------------------
# Selftest: each exit code fires on a fixture, and the command's text names no stack
# ---------------------------------------------------------------------------------------------

def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def case(ok: bool, label: str) -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        def plugin(name: str, stacks: list[dict], agents: tuple[str, ...] = ()) -> Path:
            root = base / "plugins" / name
            (root / ".claude-plugin").mkdir(parents=True)
            (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name, "version": "1.0.0"}), encoding="utf-8")
            (root / "stacks.json").write_text(json.dumps({"plugin": name, "stacks": stacks}), encoding="utf-8")
            for agent in agents:
                (root / "agents").mkdir(exist_ok=True)
                (root / "agents" / f"{agent}.md").write_text("---\nname: x\n---\n", encoding="utf-8")
            return root

        fixture_agents = plugin("fixture-agents", [], agents=("a",))

        def project(name: str, files: dict[str, str]) -> Path:
            root = base / "projects" / name
            root.mkdir(parents=True)
            for rel, body in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(body, encoding="utf-8")
            return root

        def stack(ident: str, markers: list[dict], deploy: dict | None) -> dict:
            # The detector wants every flow field declared by the plugins together; a full block keeps these fixtures about `deploy` alone.
            descriptor: dict = {"tests": {"command": ["t"], "glob": "*"}, "agents": {"developer": "fixture-agents:a", "test_runner": "fixture-agents:a", "reviewer": "fixture-agents:a"}}
            if deploy:
                descriptor["deploy"] = deploy
            return {"id": ident, "name": ident.title(), "all": markers, "descriptor": descriptor}

        alpha = {"target": "alpha-host", "artifact": "docker-image", "agent": "alpha-stack:deployer"}
        alpha_plugin = plugin("alpha-stack", [stack("alpha", [{"file": "alpha.toml"}], alpha)], agents=("deployer",))
        alpha_roots = [alpha_plugin.parent]  # one directory holds every fixture plugin, `fixture-agents` among them
        alpha_app = project("alpha-app", {"alpha.toml": ""})

        code, report = target(alpha_app, [alpha_plugin], alpha_roots)
        case(code == 0 and report.get("agent") == "alpha-stack:deployer" and report.get("target") == "alpha-host",
             f"a project of the alpha stack is routed to the descriptor's deploy agent: {code} {report}")

        # EXIT 1, never a known target: no stack, and a stack no plugin knows.
        for label, files in (("an empty project", {}), ("a project of a stack no installed plugin declares (beta.toml only)", {"beta.toml": ""})):
            code, report = target(project(label.split()[1] + str(len(files)), files), [alpha_plugin], alpha_roots)
            case(code == 1 and "agent" not in report and "alpha-host" not in json.dumps(report).replace("no deploy target", ""),
                 f"{label} stops with exit 1 and names no agent, never a known target: {code} {report}")

        # EXIT 2, never a known target: an unreadable manifest beside a project that WOULD be alpha.
        broken = plugin("broken-stack", [])
        (broken / "stacks.json").write_text("{ not json", encoding="utf-8")
        code, report = target(alpha_app, [alpha_plugin, broken], alpha_roots)
        case(code == 2 and "agent" not in report and report["problems"], f"an unreadable manifest is exit 2, and a project that WOULD be alpha is NOT defaulted to its target: {code} {report}")

        # EXIT 2: the descriptor names an agent that does not exist.
        ghost = plugin("ghost-stack", [stack("ghost", [{"file": "ghost.toml"}], {"target": "x", "artifact": "y", "agent": "ghost-stack:nobody"})])
        code, report = target(project("ghost", {"ghost.toml": ""}), [ghost], [ghost.parent])
        case(code == 2 and any("nobody" in p for p in report["problems"]), f"a descriptor naming an agent that does not exist is exit 2: {code} {report}")

        # EXIT 2: two plugins both declare a deploy target for one project (no silent pick).
        other = plugin("other-stack", [stack("other", [{"file": "other.toml"}], {"target": "other", "artifact": "zip", "agent": "other-stack:deployer"})], agents=("deployer",))
        both = project("both", {"alpha.toml": "", "other.toml": ""})
        code, report = target(both, [alpha_plugin, other], [alpha_plugin.parent])
        case(code == 2 and "agent" not in report, f"two stacks that both declare a deploy target are exit 2, not a pick: {code} {report}")

        # EXIT 1: a detected stack that declares no deploy.
        nodeploy = plugin("plain-stack", [stack("plain", [{"file": "plain.toml"}], None)])
        code, report = target(project("plain", {"plain.toml": ""}), [nodeploy], [nodeploy.parent])
        case(code == 1 and "agent" not in report and any("declares no `deploy`" in p for p in report["problems"]),
             f"a stack that declares no deploy target is exit 1: {code} {report}")

        # THE SEAM: another stack declares itself and is chosen, with no change here (any later stack's deploy agent is exactly this).
        gamma = plugin("gamma-stack", [stack("gamma", [{"file": "gamma.toml"}], {"target": "gamma", "artifact": "git-ref", "agent": "gamma-stack:gamma-deployer"})],
                        agents=("gamma-deployer",))
        code, report = target(project("gamma-app", {"gamma.toml": ""}), [alpha_plugin, gamma], [alpha_plugin.parent])
        case(code == 0 and report.get("agent") == "gamma-stack:gamma-deployer" and report.get("target") == "gamma",
             f"a stack that declares its own deploy agent is chosen by the descriptor alone: {code} {report}")

    # THE SHIPPED CALL SITE: the command asks this script, stops on 1 and 2, and names no stack.
    command = HERE.parent / "commands" / "deploy-cloud.md"
    text = command.read_text(encoding="utf-8") if command.is_file() else ""
    case(bool(text), "commands/deploy-cloud.md exists beside this script")
    case("scripts/deploy_target.py" in text, "deploy-cloud.md asks deploy_target.py which agent to delegate to")
    lowered = text.lower()
    # The words a stack-neutral command must not name are the ones the installed stack plugins declare: every stack id, plugin name,
    # deploy target and agent name in a sibling `stacks.json`. (Alone, pipeline sees no sibling and this is a weaker check; the
    # clone, where the gates run, sees them all.)
    named: set[str] = set()
    # Only in the checkout (`plugins/<name>/scripts`): a staged or installed copy sits among unrelated directories, and discovery
    # there walks them all (a mutation baseline ran past its 600 s budget that way).
    plugins_dir = HERE.parents[1]
    siblings = sorted(plugins_dir.iterdir()) if plugins_dir.name == "plugins" else []
    for manifest_dir in siblings:
        try:
            declared = json.loads((manifest_dir / "stacks.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        named.add(str(declared.get("plugin", "")).lower())
        for st in declared.get("stacks", []):
            named.add(str(st.get("id", "")).lower())
            deploy = (st.get("descriptor") or {}).get("deploy") or {}
            named.update({str(deploy.get("target", "")).lower(), str(deploy.get("agent", "")).lower().rpartition(":")[2]})
    case(not (plugins_dir / "rails-stack" / "stacks.json").is_file() or "kamal" in named, "the clone's declared stack words were collected")
    for word in sorted(named - {""}):
        case(word not in lowered, f"deploy-cloud.md is stack-neutral: it must not name `{word}`, which a stack plugin declares")
    for word in ("exit `1`", "exit `2`", "never fall back"):
        case(word in lowered, f"deploy-cloud.md says what to do on {word}")
    for tool in ("BREAKER", "SECRET_SCAN", "APM_ADVISORY", "STOP_CONDITIONS"):
        case(tool in text, f"deploy-cloud.md hands the delegated agent the absolute path of {tool}")

    if failures:
        print(f"deploy_target selftest: FAILED ({len(failures)} of {checks})")
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    print(f"deploy_target selftest: {checks} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
