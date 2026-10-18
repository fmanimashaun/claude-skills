"""Mutation guard: data_root. Declared here, run by scripts/mutation_check.py (#2141).

Each mutation removes one guard from the host script the pipeline plugin ships (`templates/data-root/bin/data-root.sh`); the template
selftest must name the case that catches it. Every one of these was a real finding on the Retask original (Retask #2094/#2130/#1969).
"""
from mutation_types import Guard, Mutation  # noqa: F401

NEEDS = ("templates/data-root/bin/data-root", "templates/data-root/kamal-hooks/pre-connect",
         "templates/data-root/kamal-hooks/post-deploy", "templates/data-root/kamal-hooks/docker-setup",
         "scripts/check_deploy_volumes.py")

GUARD = Guard(
    name="data_root",
    subject="templates/data-root/bin/data-root.sh",
    selftest="scripts/data_root_selftest.py",
    needs=NEEDS,
    mutations=(
        Mutation("a disk that already has a filesystem is formatted", 'if [ -z "$fstype" ]; then', "if true; then",
                 "our own filesystem is never formatted"),
        Mutation("the fstab line loses nofail", "defaults,nofail", "defaults", "it goes into fstab by UUID with nofail"),
        Mutation("mkfs reads the caller's stdin (the rest of the script under bash -s)", '"$device" </dev/null', '"$device"',
                 "mkfs never reads the caller's stdin"),
        Mutation("an fstab entry that is not mounted falls back to the root disk", "if awk -v root=", "if false && awk -v root=",
                 "an fstab entry for the root that is not mounted STOPS"),
        Mutation("a found foreign filesystem is adopted", 'if [ -n "$fstype" ] && [ "$(blkid -o value -s LABEL',
                 'if false && [ -n "$fstype" ] && [ "$(blkid -o value -s LABEL', "a FOUND disk with a foreign filesystem is refused"),
        Mutation("a named partitioned disk passes", '[ "$(lsblk -nlpo NAME "$device" | wc -l | tr -d \' \')" = 1 ] || die "DATA_DEVICE',
                 'true || die "DATA_DEVICE', "a NAMED partitioned disk is refused"),
        Mutation("old data not moved in is ignored", 'if [ "${#old[@]}" -gt 0 ] && [ "$MIGRATING" != 1 ] && [ ! -f "$MOVED_MARKER" ]; then',
                 "if false; then", "old data not moved in: refused"),
        Mutation("a volume mounts over data on the root disk",
                 'if [ -d "$DATA_ROOT" ] && [ -n "$(ls -A "$DATA_ROOT" 2>/dev/null)" ]; then', "if false; then",
                 "a new volume is refused while the root disk holds the data"),
        Mutation("the first of two candidate disks is taken", '*) die "${#candidates[@]} unmounted disks',
                 '*) device=${candidates[0]}; : "${#candidates[@]} unmounted disks', "two candidate disks are refused"),
    ),
)
