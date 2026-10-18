#!/usr/bin/env python3
"""Selftest for the data-root templates the pipeline plugin ships (#2141): `templates/data-root/`.

Run:  python3 data_root_selftest.py [--selftest]
Exit: 0 every case passes; 1 a case failed (named on stdout)

The host script (`bin/data-root.sh`) runs as root on a server and formats and mounts disks, so it is driven here against a FAKE host:
DATA_ROOT and FSTAB point into a temp directory, and `mountpoint`, `findmnt`, `lsblk`, `blkid`, `mkfs.ext4`, `mount`, `chown`, `readlink`
and `docker` are stubs on PATH that log their argv and answer from FAKE_* variables. The local scripts (`bin/data-root`, the
`pre-connect` and `post-deploy` hooks) run with a stub `ssh` and a stub `bin/kamal`. Nothing touches a disk, a host or Docker.
Every guard below is held by `scripts/mutations/data_root.py`: each mutant removes one, and a case here must fail.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "data-root"
FAILURES: list[str] = []
CHECKS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILURES.append(f"{label}: {detail}")


STUBS = {
    "findmnt": """case "$*" in
  "-nvo SOURCE /") echo /dev/nvme0n1p1 ;;
  *"-S /dev/"*) [[ " ${FAKE_MOUNTED_DISKS:-} " == *" ${@: -1} "* ]] && echo /mnt/elsewhere ;;
  *SOURCE*) echo /dev/nvme1n1 ;;
esac
exit 0""",
    "lsblk": """case "$*" in
  "-dno TYPE /dev/"*) dev=${@: -1}; for d in nvme0n1 ${FAKE_DISKS:-}; do [ "/dev/${d%%:*}" = "$dev" ] && echo disk; done ;;
  "-no PKNAME /dev/nvme0n1p1") echo nvme0n1 ;;
  "-dnbpo NAME,TYPE,SIZE") echo "/dev/nvme0n1 disk 8589934592"; for d in ${FAKE_DISKS:-}; do echo "/dev/${d%%:*} disk 10737418240"; done; echo "/dev/loop0 loop 1024"; echo "/dev/nbd0 disk 0" ;;
  "-nlpo NAME "*) dev=${@: -1}; n=1
    for d in ${FAKE_DISKS:-}; do [ "/dev/${d%%:*}" = "$dev" ] && n=${d##*:}; done
    [ "$dev" = /dev/nvme0n1 ] && n=2
    for i in $(seq "$n"); do echo "$dev$i"; done ;;
esac
exit 0""",
    "blkid": """case "$*" in
  *"-s TYPE"*) { [ -n "${FAKE_FSTYPE:-}" ] || [ -f "$STATE/formatted" ]; } && echo "${FAKE_FSTYPE:-ext4}" ;;
  *"-s UUID"*) echo "${FAKE_UUID:-1111-2222}" ;;
  *"-s LABEL"*) echo "${FAKE_LABEL:-}" ;;
esac
exit 0""",
    "mkfs.ext4": 'touch "$STATE/formatted"; cat > "$STATE/mkfs-stdin"',
    "mount": 'touch "$STATE/mounted"',
    "mountpoint": '[ -f "$STATE/mounted" ] || [ -n "${FAKE_ALREADY_MOUNTED:-}" ]',
    "chown": "exit 0",
    "readlink": 'echo "${@: -1}"',
    "docker": '[ "$*" = "volume inspect old_storage" ] && [ -n "${FAKE_OLD_VOLUME:-}" ]',
}


class Host:
    """A temp directory standing in for one server: the stubs, the data root, fstab and a state dir."""

    def __init__(self, base: Path, script: Path | None = None):
        self.base = base
        self.stubs = base / "stubs"
        self.stubs.mkdir(parents=True)
        self.log = base / "calls.log"
        self.state = base / "state"
        self.state.mkdir()
        self.root = base / "srv" / "shop"
        self.fstab = base / "fstab"
        self.fstab.write_text("UUID=root-uuid / ext4 defaults 0 1\n")
        self.script = script or TEMPLATES / "bin" / "data-root.sh"
        for name, body in STUBS.items():
            path = self.stubs / name
            path.write_text(f'#!/usr/bin/env bash\nprintf \'%s %s\\n\' {name} "$*" >> "$CALLS"\n{body}\n')
            path.chmod(0o755)

    def run(self, *args: str, **fake: str) -> tuple[int, str, list[str]]:
        env = {**os.environ, "PATH": f"{self.stubs}:{os.environ['PATH']}", "CALLS": str(self.log), "STATE": str(self.state),
               "DATA_ROOT": str(self.root), "FSTAB": str(self.fstab), "LEGACY_DATA": ""}
        for key in ("DATA_DEVICE", "DATA_DEVICE_ADOPT", "LEGACY_DATA"):
            if key.lower() in fake:
                env[key] = fake.pop(key.lower())
        env.update({f"FAKE_{k.upper()}": v for k, v in fake.items()})
        done = subprocess.run(["bash", str(self.script), *args], env=env, capture_output=True, text=True,
                              input="THE REST OF THE SCRIPT, AS bash -s READS IT\n", timeout=120)
        calls = self.log.read_text().splitlines() if self.log.exists() else []
        return done.returncode, done.stdout + done.stderr, calls


def host_cases(tmp: Path, script: Path | None = None) -> None:
    def fresh(name: str) -> Host:
        return Host(tmp / name, script)

    def touched(calls: list[str]) -> bool:
        return any(c.startswith(("mkfs", "mount ")) for c in calls)

    h = fresh("no-volume")
    code, out, calls = h.run()
    check("no data volume: the root disk, with a warning", code == 0 and "WARNING: no data volume is attached" in out and not touched(calls), out)
    check("no data volume: the app's storage subdirectory is made", (h.root / "storage").is_dir(), "")

    h = fresh("blank")
    code, out, calls = h.run(disks="nvme1n1:1", uuid="abcd-1234")
    check("a blank volume is formatted with our label", "mkfs.ext4 -q -L data-root /dev/nvme1n1" in calls, out)
    check("it goes into fstab by UUID with nofail", f"UUID=abcd-1234 {h.root} ext4 defaults,nofail 0 2\n" in h.fstab.read_text(), h.fstab.read_text())
    check("it is mounted", f"mount {h.root}" in calls and code == 0, out)
    check("mkfs never reads the caller's stdin (bash -s feeds it the script)", (h.state / "mkfs-stdin").read_text() == "", "")

    h = fresh("ours-twice")
    for _ in range(2):
        h.run(disks="nvme1n1:1", fstype="xfs", label="data-root")
    calls = h.log.read_text().splitlines()
    check("our own filesystem is never formatted", not any(c.startswith("mkfs") for c in calls), "")
    check("the fstab line is added once however often it runs", h.fstab.read_text().count("UUID=1111-2222") == 1, h.fstab.read_text())

    h = fresh("mounted")
    code, out, calls = h.run(disks="nvme1n1:1", already_mounted="1")
    check("already mounted: nothing changes", code == 0 and "already mounted" in out and not touched(calls), out)

    h = fresh("foreign-found")
    code, out, calls = h.run(disks="nvme1n1:1", fstype="ext4", label="backups")
    check("a FOUND disk with a foreign filesystem is refused", code != 0 and "not labelled data-root" in out and not touched(calls), out)

    h = fresh("two")
    code, out, calls = h.run(disks="nvme1n1:1 nvme2n1:1")
    check("two candidate disks are refused until DATA_DEVICE names one", code != 0 and "2 unmounted disks" in out and not h.root.exists(), out)

    h = fresh("named-partitioned")
    code, out, calls = h.run(disks="nvme2n1:3", data_device="/dev/nvme2n1")
    check("a NAMED partitioned disk is refused, never formatted", code != 0 and "has partitions" in out and not touched(calls), out)

    h = fresh("named-foreign")
    code, out, calls = h.run(disks="nvme1n1:1", fstype="xfs", label="backups", data_device="/dev/nvme1n1")
    check("a NAMED foreign filesystem is refused without DATA_DEVICE_ADOPT", code != 0 and "DATA_DEVICE_ADOPT=1" in out, out)
    code, out, calls = h.run(disks="nvme1n1:1", fstype="xfs", label="backups", data_device="/dev/nvme1n1", data_device_adopt="1")
    check("...and mounted unformatted with it", code == 0 and not any(c.startswith("mkfs") for c in calls) and f"mount {h.root}" in calls, out)

    h = fresh("fstab-gone")
    h.fstab.write_text(h.fstab.read_text() + f"UUID=gone {h.root}/ ext4 defaults,nofail 0 2\n")
    code, out, calls = h.run()
    check("an fstab entry for the root that is not mounted STOPS (trailing slash too)",
          code != 0 and "did not come back" in out and "WARNING" not in out and not h.root.exists(), out)

    h = fresh("data-on-root")
    (h.root / "postgres").mkdir(parents=True)
    (h.root / "postgres" / "PG_VERSION").write_text("18")
    code, out, calls = h.run(disks="nvme1n1:1")
    check("a new volume is refused while the root disk holds the data", code != 0 and "already holds data" in out and not touched(calls), out)

    h = fresh("legacy")
    old = h.base / "old-pg"
    old.mkdir()
    (old / "PG_VERSION").write_text("16")
    legacy = f"volume:old_storage dir:{old}"
    code, out, calls = h.run(legacy_data=legacy, old_volume="1")
    check("old data not moved in: refused", code != 0 and "data still in the old places" in out and not h.root.exists(), out)
    code, out, calls = h.run("--migrating", legacy_data=legacy, old_volume="1")
    check("...the move's --migrating argument prepares the empty root", code == 0 and (h.root / "storage").is_dir(), out)
    code, out, calls = h.run("--force", legacy_data=legacy, old_volume="1")
    check("...any other argument is refused", code != 0 and "unknown argument" in out, out)
    (h.root / ".moved-into-data-root").write_text("moved\n")
    code, out, calls = h.run(legacy_data=legacy, old_volume="1")
    check("...once the move has marked the root, deploys pass (even with no stored files)", code == 0, out)


def local_cases(tmp: Path) -> None:
    project = tmp / "project"
    (project / "bin").mkdir(parents=True)
    (project / ".kamal" / "hooks").mkdir(parents=True)
    (project / "config").mkdir()
    for f in ("data-root", "data-root.sh"):
        shutil.copy(TEMPLATES / "bin" / f, project / "bin" / f)
    for f in ("pre-connect", "post-deploy", "docker-setup"):
        shutil.copy(TEMPLATES / "kamal-hooks" / f, project / ".kamal" / "hooks" / f)
    shutil.copy(Path(__file__).resolve().parent / "check_deploy_volumes.py", project / "bin" / "check-deploy-volumes")
    (project / "config" / "deploy.yml").write_text('service: shop\nvolumes:\n  - "/srv/shop/storage:/rails/storage"\n')
    stubs = tmp / "local-stubs"
    stubs.mkdir()
    log = tmp / "local.log"
    (stubs / "ssh").write_text(f'#!/usr/bin/env bash\nprintf \'ssh %s | stdin %s\\n\' "$*" "$(head -1)" >> "{log}"\n')
    (project / "bin" / "kamal").write_text(f'#!/usr/bin/env bash\nprintf \'kamal %s\\n\' "$*" >> "{log}"\nexit ${{FAKE_PRUNE_EXIT:-0}}\n')
    for p in [*stubs.iterdir(), *(project / "bin").iterdir(), *(project / ".kamal" / "hooks").iterdir()]:
        p.chmod(0o755)

    def run(path: str, **env: str) -> tuple[int, str, list[str]]:
        if log.exists():
            log.unlink()
        full = {**{k: v for k, v in os.environ.items() if not k.startswith(("KAMAL_", "DATA_", "LEGACY_"))},
                "PATH": f"{stubs}:{os.environ['PATH']}", **env}
        done = subprocess.run([str(project / path)], env=full, capture_output=True, text=True, timeout=120)
        return done.returncode, done.stdout + done.stderr, log.read_text().splitlines() if log.exists() else []

    for pair in ("deploy:", "redeploy:", "setup:", "app:boot", "accessory:boot", "accessory:reboot", "accessory:start"):
        command, subcommand = pair.split(":")
        code, out, calls = run(".kamal/hooks/pre-connect", KAMAL_COMMAND=command, KAMAL_SUBCOMMAND=subcommand, KAMAL_HOSTS="203.0.113.10,203.0.113.11")
        check(f"pre-connect reaches every host for {pair}", code == 0 and len(calls) == 2 and "DATA_ROOT='/srv/shop'" in calls[0], out + str(calls))
    for pair in ("app:logs", "app:details", "accessory:exec", "prune:all"):
        command, subcommand = pair.split(":")
        code, out, calls = run(".kamal/hooks/pre-connect", KAMAL_COMMAND=command, KAMAL_SUBCOMMAND=subcommand, KAMAL_HOSTS="203.0.113.10")
        check(f"pre-connect does nothing for {pair}", code == 0 and calls == [], str(calls))

    (project / "config" / "deploy.yml").write_text('service: shop\nvolumes:\n  - "shop_storage:/rails/storage"\n')
    code, out, calls = run(".kamal/hooks/pre-connect", KAMAL_COMMAND="deploy", KAMAL_HOSTS="203.0.113.10")
    check("pre-connect refuses a named volume before reaching any host", code != 0 and "named Docker volume" in out and calls == [], out)
    code, out, calls = run(".kamal/hooks/docker-setup", KAMAL_HOSTS="203.0.113.10")
    check("docker-setup refuses it too", code != 0 and calls == [], out)
    (project / "config" / "deploy.yml").write_text('service: shop\nvolumes:\n  - "/srv/shop/storage:/rails/storage"\n')

    code, out, calls = run("bin/data-root", DATA_DEVICE="/dev/x'; reboot #", WEB_HOST="203.0.113.10")
    check("bin/data-root refuses a value that could break out of the ssh command", code != 0 and calls == [], out)
    code, out, calls = run("bin/data-root", KAMAL_HOSTS="host;reboot")
    check("bin/data-root refuses a strange host", code != 0 and calls == [], out)

    for command in ("redeploy", "rollback"):
        code, out, calls = run(".kamal/hooks/post-deploy", KAMAL_COMMAND=command)
        check(f"post-deploy prunes after {command}", code == 0 and calls == ["kamal prune all"], str(calls))
    code, out, calls = run(".kamal/hooks/post-deploy", KAMAL_COMMAND="redeploy", KAMAL_DESTINATION="staging")
    check("post-deploy passes the destination", calls == ["kamal prune all -d staging"], str(calls))
    code, out, calls = run(".kamal/hooks/post-deploy", KAMAL_COMMAND="deploy")
    check("post-deploy does not prune twice after a deploy", code == 0 and calls == [], str(calls))
    code, out, calls = run(".kamal/hooks/post-deploy", KAMAL_COMMAND="redeploy", FAKE_PRUNE_EXIT="1")
    check("a failed prune warns and does not fail the live release", code == 0 and "WARNING" in out, out)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        host_cases(Path(tmp) / "hosts")
        local_cases(Path(tmp) / "local")
    if FAILURES:
        print(f"data_root selftest FAILED -- {len(FAILURES)} of {CHECKS} checks:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"data_root selftest: {CHECKS} checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
