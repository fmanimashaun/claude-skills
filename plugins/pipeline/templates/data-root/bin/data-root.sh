#!/usr/bin/env bash
# THE DATA ROOT (shipped by the claude-skills `pipeline` plugin, #2141; proven first on a production Retask host, Retask #2094 and #2130).
# Every byte production keeps lives under ONE directory, $DATA_ROOT (`/srv/<service>` by default), so moving it to a new disk is one copy
# and one mount. `config/deploy.yml` bind-mounts each persistent volume under it (the app's `volumes:`, each accessory's `directories:`),
# and `bin/check-deploy-volumes` refuses anything else. This script makes that directory exist, on the right disk, BEFORE a container that
# mounts it starts. It runs ON THE HOST, as root, piped over ssh by `bin/data-root` (from the `pre-connect` and `docker-setup` hooks):
#
#   ssh root@HOST "DATA_ROOT=/srv/<service> bash -s" < bin/data-root.sh
#
# The cases, in order:
#   0. OLD DATA NOT MOVED: LEGACY_DATA names where the data lived before (`volume:<docker volume>` and `dir:<host path>`, space-separated);
#      while any of them still holds data and $DATA_ROOT/.moved-into-data-root is absent, this STOPS, because a deploy now would boot the app on
#      an empty data root. The move (reference/data-root.md, "Moving existing data in") writes that marker last; it is the one caller that
#      passes `--migrating` (an ARGUMENT, never an environment variable a deploy could inherit) to prepare the empty root it then fills.
#   1. ALREADY MOUNTED: $DATA_ROOT is a mount point. Nothing is formatted or mounted; the app's subdirectories are made sure of.
#   1b. NOT BACK: /etc/fstab names $DATA_ROOT but it is not mounted (a volume that did not come back). It STOPS: carrying on would put an
#      empty data root on the root disk.
#   2. A DATA VOLUME IS ATTACHED: exactly one block disk that is not the root disk, not empty (size 0), with no partitions and not mounted
#      (an EBS volume as nvme1n1 or xvdf), or the disk DATA_DEVICE names. A disk it FINDS is adopted only when blank or labelled
#      $DATA_LABEL; a NAMED one meets the same checks, and one carrying another filesystem needs DATA_DEVICE_ADOPT=1 (mounted as it is,
#      never formatted). It is formatted ext4 ONLY when it carries no filesystem, added to /etc/fstab BY UUID with `nofail` (a missing
#      volume must not stop the host booting), and mounted at $DATA_ROOT.
#   3. NO DATA VOLUME: $DATA_ROOT is made on the root disk with a WARNING line, and the deploy carries on.
# It REFUSES, before changing anything: two or more candidate disks with no DATA_DEVICE; a volume attached while $DATA_ROOT already holds
# data on the root disk (mounting would hide it: that is the runbook's move, never a deploy).
#
# Paths and the commands it calls can be overridden for the selftest; production uses the defaults.
set -euo pipefail

DATA_ROOT=${DATA_ROOT:?set DATA_ROOT (bin/data-root passes /srv/<service>)}
FSTAB=${FSTAB:-/etc/fstab}
DATA_DEVICE=${DATA_DEVICE:-}
DATA_DEVICE_ADOPT=${DATA_DEVICE_ADOPT:-}   # 1: mount a NAMED disk that carries a filesystem other than ours, as it is
LEGACY_DATA=${LEGACY_DATA:-}             # where the data lived before the data root: "volume:<name> dir:<path> ..."; empty on a new host
DATA_LABEL=${DATA_LABEL:-data-root}      # the ext4 label this script gives a volume it formats, and recognises as ours
APP_SUBDIRS=${APP_SUBDIRS:-storage}      # the app's bind mounts under the root (Kamal does NOT create `volumes:` paths); owned by APP_UID
APP_UID=${APP_UID:-1000}                 # the Rails Dockerfile's `rails` user (USER 1000:1000)
MIGRATING=0
case "${1:-}" in
  --migrating) MIGRATING=1 ;;
  '') ;;
  *) echo "data-root: STOP: unknown argument '$1' (the only one is --migrating, passed by the move into the data root)" >&2; exit 1 ;;
esac
case "$DATA_ROOT" in /?*) ;; *) echo "data-root: STOP: DATA_ROOT must be an absolute directory below /, not '$DATA_ROOT'" >&2; exit 1 ;; esac
[ "$DATA_ROOT" != / ] || { echo "data-root: STOP: DATA_ROOT must not be /" >&2; exit 1; }

say() { echo "data-root: $*"; }
warn() { echo "data-root: WARNING: $*" >&2; }
die() { echo "data-root: STOP: $*" >&2; exit 1; }

subdirs() {
  # Accessory `directories:` are made by Kamal itself (with `mode`/`owner`); the app's `volumes:` paths are not, so they are made here.
  for d in $APP_SUBDIRS; do mkdir -p "$DATA_ROOT/$d"; chown "$APP_UID:$APP_UID" "$DATA_ROOT/$d"; done
}

# 0. The old data is still in the old places, and the data root is not filled: a deploy now would boot on nothing.
old=()
for place in $LEGACY_DATA; do
  case "$place" in
    volume:?*) if command -v docker >/dev/null 2>&1 && docker volume inspect "${place#volume:}" >/dev/null 2>&1; then old+=("the Docker volume ${place#volume:}"); fi ;;
    dir:/?*) d=${place#dir:}; [ -d "$d" ] && [ -n "$(ls -A "$d" 2>/dev/null)" ] && old+=("$d") ;;
    *) die "LEGACY_DATA entry '$place' is neither volume:<name> nor dir:<absolute path>" ;;
  esac
done
MOVED_MARKER="$DATA_ROOT/.moved-into-data-root"   # written by the move into the data root once the data is copied and checked
if [ "${#old[@]}" -gt 0 ] && [ "$MIGRATING" != 1 ] && [ ! -f "$MOVED_MARKER" ]; then
  die "data still in the old places (${old[*]}) and $MOVED_MARKER is absent: move it in first (reference/data-root.md, \"Moving existing data in\"). A deploy now would boot the app on an empty $DATA_ROOT. Nothing was changed."
fi

# 1. Already a mount point: the volume (or whatever the operator mounted) is in place.
if mountpoint -q "$DATA_ROOT"; then
  subdirs
  say "$DATA_ROOT is already mounted ($(findmnt -nro SOURCE "$DATA_ROOT"))"
  exit 0
fi

# 1b. fstab says a volume belongs here, but it is not mounted: it did not come back (detached, failed, `nofail` let the host boot).
# Never fall through to the root disk: that is an empty data root, an empty Postgres, and the real data somewhere else.
# The mount point compared with trailing slashes removed, so a hand-edited `$DATA_ROOT/` is the same entry.
if awk -v root="$DATA_ROOT" 'BEGIN { sub(/\/+$/, "", root) } $1 !~ /^#/ { m = $2; sub(/\/+$/, "", m); if (m == root) found = 1 } END { exit !found }' "$FSTAB"; then
  die "$FSTAB names $DATA_ROOT but it is not mounted: the volume did not come back. Check it is attached (lsblk), then mount $DATA_ROOT, and rerun. Nothing was changed."
fi

# 2. Which disk, if any. The root disk is the parent of whatever holds /.
root_source=$(findmnt -nvo SOURCE /) || die "cannot read what / is mounted from"
root_disk=$(lsblk -no PKNAME "$root_source" 2>/dev/null | head -1 || true)   # `|| true`: a root that is no block device (overlay, a container) is not an error
root_disk=${root_disk:+/dev/$root_disk}
[ -n "$root_disk" ] || root_disk=$root_source       # / on a whole disk, no partition table

device=""
if [ -n "$DATA_DEVICE" ]; then
  device=$(readlink -f "$DATA_DEVICE" 2>/dev/null || true)
  case "$(lsblk -dno TYPE "$device" 2>/dev/null || true)" in disk|loop) ;; *) die "DATA_DEVICE '$DATA_DEVICE' is not a whole block disk on this host" ;; esac   # a NAMED loop device is the operator's choice; a FOUND one never is
  [ "$device" != "$root_disk" ] || die "DATA_DEVICE '$DATA_DEVICE' is the root disk"
  [ "$(lsblk -nlpo NAME "$device" | wc -l | tr -d ' ')" = 1 ] || die "DATA_DEVICE '$DATA_DEVICE' ($device) has partitions: name a bare disk, never one that is partitioned"
  [ -z "$(findmnt -rno TARGET -S "$device" || true)" ] || die "DATA_DEVICE '$DATA_DEVICE' ($device) is already mounted at $(findmnt -rno TARGET -S "$device" | head -1)"
else
  candidates=()
  while read -r name type size; do
    [ "$type" = disk ] || continue
    [ "${size:-0}" != 0 ] || continue                                        # an empty slot (an unattached nbd device) is no disk
    [ "$name" != "$root_disk" ] || continue
    [ "$(lsblk -nlpo NAME "$name" | wc -l | tr -d ' ')" = 1 ] || continue   # it has partitions: not a bare data volume
    [ -z "$(findmnt -rno TARGET -S "$name" || true)" ] || continue            # already mounted somewhere else
    candidates+=("$name")
  done < <(lsblk -dnbpo NAME,TYPE,SIZE)
  case ${#candidates[@]} in
    0) ;;
    1) device=${candidates[0]} ;;
    *) die "${#candidates[@]} unmounted disks are attached (${candidates[*]}): set DATA_DEVICE in .kamal/deploy.env to the one for $DATA_ROOT" ;;
  esac
fi

# 3. No data volume: the root disk, with a warning.
if [ -z "$device" ]; then
  mkdir -p "$DATA_ROOT"
  subdirs
  warn "no data volume is attached: $DATA_ROOT is on the root disk ($root_disk). Attach a volume and follow reference/data-root.md, \"Moving the data root to a new volume\", to move it."
  exit 0
fi

# A volume is attached but the root disk already holds the data: mounting would hide it. The move is a runbook step.
if [ -d "$DATA_ROOT" ] && [ -n "$(ls -A "$DATA_ROOT" 2>/dev/null)" ]; then
  die "$device is attached and $DATA_ROOT already holds data on the root disk; mounting over it would hide that data. Move it first: reference/data-root.md, \"Moving the data root to a new volume\"."
fi

fstype=$(blkid -o value -s TYPE "$device" 2>/dev/null || true)
# A disk FOUND (not named) is adopted only when it is blank or already ours: one carrying another filesystem may be somebody's data.
if [ -n "$fstype" ] && [ "$(blkid -o value -s LABEL "$device" 2>/dev/null || true)" != "$DATA_LABEL" ] && [ "$DATA_DEVICE_ADOPT" != 1 ]; then
  if [ -z "$DATA_DEVICE" ]; then
    die "$device carries a $fstype filesystem that is not labelled $DATA_LABEL: if it is the one for $DATA_ROOT, set DATA_DEVICE=$device and DATA_DEVICE_ADOPT=1 in .kamal/deploy.env"
  fi
  die "DATA_DEVICE $device carries a $fstype filesystem that is not ours (label $DATA_LABEL): set DATA_DEVICE_ADOPT=1 to mount it as it is (it is never formatted)"
fi
if [ -z "$fstype" ]; then
  say "formatting $device (ext4, label $DATA_LABEL): it carries no filesystem"
  mkfs.ext4 -q -L "$DATA_LABEL" "$device" </dev/null   # </dev/null: mkfs must never stop to ask, over a non-interactive ssh
  fstype=ext4
fi
uuid=$(blkid -o value -s UUID "$device") || die "cannot read the UUID of $device"
[ -n "$uuid" ] || die "$device has no UUID"
if ! grep -qE "^[[:space:]]*UUID=$uuid[[:space:]]" "$FSTAB"; then
  printf 'UUID=%s %s %s defaults,nofail 0 2\n' "$uuid" "$DATA_ROOT" "$fstype" >> "$FSTAB"
  say "added UUID=$uuid to $FSTAB (nofail)"
fi
mkdir -p "$DATA_ROOT"
mount "$DATA_ROOT"
mountpoint -q "$DATA_ROOT" || die "mount $DATA_ROOT did not mount $device"
subdirs
say "$device (UUID=$uuid, $fstype) is mounted at $DATA_ROOT"
