# shellcheck shell=bash
# trusted-env.sh -- the environment every hook runs in (#1850, P1 of #1843).
#
# SOURCED, never executed: the first executable line of every hook script, before any `python3`, `git` or `gh`.
#
# WHY. A repository's checked-in `.claude/settings.json` `env` reaches every hook process (measured on #1843,
# docs/evidence/audits/2026-10-11-hook-environment-1843.md). A hook then resolved `python3`, `git` and `gh` through a PATH the
# repository chose, honoured its PYTHONPATH and GIT_CONFIG_* and, started with a bare `bash`, sourced its BASH_ENV. This lib closes the
# COOPERATING case: a project that legitimately puts a `bin/git` shim on PATH, a direnv, a stray variable. It does NOT close the hostile
# one (a project's settings can still set `disableAllHooks`); the trust decision stays the boundary, and docs/doctrine/harness-doctrine.md says so.
#
# WHAT IT DOES, once, at source time:
#   rf_scrub_env      unsets PYTHON*, LD_*, DYLD_*, NODE_OPTIONS, BASH_ENV, ENV, SHELLOPTS, BASHOPTS, CDPATH, GLOBIGNORE and every GIT_*
#                     outside RF_GIT_ALLOW (GIT_CONFIG_*, GIT_EXEC_PATH, GIT_ASKPASS, GIT_SSH* are dropped).
#   rf_trusted_path   rebuilds PATH from ABSOLUTE entries that are not at or inside the repository (the OUTERMOST of the Gemfile and .git
#                     ancestors of $PWD), each resolved through its symlinks, so the bare-name calls below it find the system's tools.
#   rf_trusted_python (on demand) sets RF_PYTHON to a python3 whose own symlink TARGET is outside the repository too.
#
# REQUIREMENTS, each of which cost a review round on #1826:
#   * shell BUILTINS only (a `dirname` is "command not found" on a PATH holding a bash and a python3 and nothing else);
#   * every loop BOUNDED (an unbounded `while` once spun forever);
#   * `set -f` around any `for dir in $PATH`, so a `*` in an entry is not globbed against the filesystem;
#   * `readlink` only from /usr/bin or /bin, never found through PATH;
#   * bash 3.2 only (macOS ships it as /bin/bash): no `mapfile`, `declare -A`, `${x,,}`, `&>>`, `coproc`;
#   * a symlink whose TARGET is inside the repository is refused;
#   * a stray `~/.git` or `~/Gemfile` makes the home directory the repository, which drops the tools installed under it: QUIET, never wrong.

# GIT_* names a hook may keep: they select a repository or an identity and run no program.
RF_GIT_ALLOW=" GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_CEILING_DIRECTORIES GIT_DISCOVERY_ACROSS_FILESYSTEM GIT_CONFIG_NOSYSTEM GIT_TERMINAL_PROMPT GIT_OPTIONAL_LOCKS GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_AUTHOR_DATE GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL GIT_COMMITTER_DATE "

rf_physical() { (cd -P "$1" 2>/dev/null && pwd -P); }

# RF_REPO_ROOT: the outermost ancestor of the working directory that holds a Gemfile or a .git (looked for by existence; git is never run).
rf_repo_root() {
  local here probe depth=0
  RF_REPO_ROOT=""
  here="$(rf_physical "$PWD")" || return 1
  RF_REPO_ROOT="$here"
  probe="$here"
  while [ "$depth" -lt 64 ]; do
    if [ -e "$probe/Gemfile" ] || [ -e "$probe/.git" ]; then RF_REPO_ROOT="$probe"; fi
    [ "$probe" = "/" ] && break
    probe="${probe%/*}"
    [ -n "$probe" ] || probe="/"
    depth=$((depth + 1))
  done
  return 0
}

# Is the absolute, physical path $1 at or inside the repository? An unresolvable working directory leaves no root, which excludes nothing.
rf_inside() {
  [ -n "${RF_REPO_ROOT:-}" ] || return 1
  case "$1/" in "$RF_REPO_ROOT"/*) return 0 ;; esac
  return 1
}

rf_scrub_env() {
  local name
  for name in $(compgen -v); do
    case "$name" in
      PYTHON*|LD_*|DYLD_*|NODE_OPTIONS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE) unset "$name" 2>/dev/null ;;
      GIT_*) case "$RF_GIT_ALLOW" in *" $name "*) ;; *) unset "$name" 2>/dev/null ;; esac ;;
    esac
  done
  return 0
}

rf_trusted_path() {
  local old_ifs="$IFS" had_f=1 dir real out="" n=0
  case $- in *f*) ;; *) had_f=0 ;; esac
  rf_repo_root
  IFS=:
  set -f
  for dir in ${PATH:-}; do
    n=$((n + 1))
    [ "$n" -le 256 ] || break
    case "$dir" in /*) ;; *) continue ;; esac
    real="$(rf_physical "$dir")" || continue
    if rf_inside "$real"; then continue; fi
    case ":$out:" in *":$real:"*) continue ;; esac
    out="${out:+$out:}$real"
  done
  IFS="$old_ifs"
  [ "$had_f" = 1 ] || set +f
  # Nothing trusted left: a PATH that finds NO program, never an empty one (a zero-length PATH is the current directory, the repository).
  [ -n "$out" ] || out="/nonexistent"
  PATH="$out"
  export PATH
  return 0
}

# The final, physical location of a file after following its link chain (16 hops), through a `readlink` taken from a fixed system location.
rf_target_of() {
  local f="$1" hops=0 t d readlink_bin="" candidate
  for candidate in /usr/bin/readlink /bin/readlink; do
    if [ -x "$candidate" ]; then readlink_bin="$candidate"; break; fi
  done
  while [ -L "$f" ]; do
    { [ "$hops" -lt 16 ] && [ -n "$readlink_bin" ]; } || return 1
    t="$("$readlink_bin" "$f")" || return 1
    case "$t" in /*) f="$t" ;; *) f="${f%/*}/$t" ;; esac
    hops=$((hops + 1))
  done
  d="$(rf_physical "${f%/*}")" || return 1
  printf '%s\n' "$d/${f##*/}"
}

# RF_PYTHON: the first python3 on PATH whose directory AND link target are outside the repository, or empty.
rf_trusted_python() {
  local old_ifs="$IFS" had_f=1 dir real target n=0
  RF_PYTHON=""
  case $- in *f*) ;; *) had_f=0 ;; esac
  [ -n "${RF_REPO_ROOT+x}" ] || rf_repo_root
  IFS=:
  set -f
  for dir in ${PATH:-}; do
    n=$((n + 1))
    [ "$n" -le 256 ] || break
    case "$dir" in /*) ;; *) continue ;; esac
    real="$(rf_physical "$dir")" || continue
    if rf_inside "$real"; then continue; fi
    if [ -x "$real/python3" ]; then
      target="$(rf_target_of "$real/python3")" || continue
      if rf_inside "$target"; then continue; fi
      RF_PYTHON="$real/python3"
      break
    fi
  done
  IFS="$old_ifs"
  [ "$had_f" = 1 ] || set +f
  return 0
}

rf_scrub_env
rf_trusted_path
RF_TRUSTED_ENV=1
