# deadline.sh -- a wall-clock deadline for a hook's work, in pure bash 3.2 (#1575).
#
# A PreToolUse hook that spins blocks every Bash call, and Claude Code's own timeout stops WAITING for it
# without killing its descendants: `awk` children ran for 51 minutes and one for 23 hours, and the machine's
# load reached 348. So the work runs in its OWN process group under a deadline, and the whole group is killed.
#
#   deadline_seconds <default> <max>     sets _deadline_s from RAILS_FLOW_HOOK_DEADLINE (an integer >= 1), else the
#                                        default; never above <max> (more than 4 digits IS <max>), which must stay
#                                        under the hook's own timeout
#   deadline_run <seconds> <fn> [args]   runs <fn> and returns its status; 137 when the deadline, or the death of
#                                        this shell, killed the group. The caller decides what 137 MEANS.
#
# Each part is here for a measured reason (macOS /bin/bash 3.2.57, prototyped before it was written):
#  * `set -m` gives a background job its OWN process group; the child is ONE simple command, so `$!` is its pid
#    AND its group id. In a pipeline `$!` is the LAST process and the group is named by the FIRST, so
#    `kill -- -$!` named a group that did not exist and an orphaned `sleep 300` outlived it.
#  * The watchdog is in a separate group and polls this shell every second, so if Claude Code SIGKILLs the hook
#    at ITS timeout, the child group dies within a second instead of running on for the full deadline.
#  * The shell prints job-control notices ("Killed: 9", "child setpgid ...") on its own stderr, which is what
#    Claude reads. Fd 2 is closed to /dev/null while supervising and the child gets the real stderr on fd 9.
#  * The watchdog holds NO pipe of the caller's (</dev/null >/dev/null): a straggling `sleep` kept stdout open
#    and a reader waiting for EOF stalled for a full second on 1% of runs; with this, the slowest of 2000 was 24 ms.
#  * No `sleep` on PATH: the watchdog loop would spin, reach the deadline at once and DENY EVERYTHING. A deadline
#    that cannot wait is no deadline, so the work runs unsupervised -- the rules still run, only the backstop is gone.
# Builtins only: `kill`, `wait`, `set`, `exec`; the one external is `sleep`, checked for.

deadline_seconds() {
  _deadline_s="${RAILS_FLOW_HOOK_DEADLINE:-$1}"
  case "$_deadline_s" in ''|*[!0-9]*) _deadline_s="$1" ;; esac
  # CLAMP BY LENGTH BEFORE ANY ARITHMETIC: bash's `[ -gt ]` and `$(( ))` fail or wrap on 19+ digits (past 2^63), and
  # a failed comparison left the value unclamped, so the watchdog's loop fell through at once and the hook denied
  # EVERY command (#1602 review F2). Five digits is far above any ceiling, so it is the ceiling.
  [ "${#_deadline_s}" -gt 4 ] && _deadline_s="$2"
  _deadline_s=$((10#$_deadline_s))             # "0008" is 8, never octal; "00" is 0
  [ "$_deadline_s" -lt 1 ] && _deadline_s="$1"  # zero would fire at once and deny everything
  [ "$_deadline_s" -gt "$2" ] && _deadline_s="$2"
  return 0
}

deadline_run() {
  local _d="$1"; shift
  local _parent=$$ _child _wd _rc _i
  if ! type -P sleep >/dev/null 2>&1; then
    ( "$@" ); return $?
  fi
  exec 9>&2 2>/dev/null
  set -m
  ( exec 2>&9 9>&-; "$@" ) &
  _child=$!
  (
    _i=0
    while [ "$_i" -lt "$_d" ]; do
      sleep 1
      kill -0 "$_parent" 2>/dev/null || break
      _i=$((_i + 1))
    done
    kill -KILL -- "-$_child" 2>/dev/null
  ) </dev/null >/dev/null 9>&- &
  _wd=$!
  wait "$_child"; _rc=$?
  # By pid FIRST, then by group: a group kill that missed would leave `wait` blocked for the whole deadline.
  # Reaped here, while fd 2 is still /dev/null, so bash's late "Killed: 9" notice for it goes nowhere.
  kill -KILL "$_wd" 2>/dev/null; kill -KILL -- "-$_wd" 2>/dev/null
  wait "$_wd" 2>/dev/null
  set +m
  exec 2>&9 9>&-
  return "$_rc"
}
