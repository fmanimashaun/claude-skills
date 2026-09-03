#!/usr/bin/env bash
# normalize_cmd.sh — turn a raw Bash tool command into the INVOKED command segments (#906).
#
# Sourced by guard-bash.sh (rails-flow) and release-gate.sh (qa-flow). Plugins install alone, so each
# ships its own copy of this file; the maintainer lint `hook-lib-drift` refuses a byte that differs
# between the two copies. Edit one, copy to the other — never let them diverge (#699: a bug survived
# its own discovery because only one of two copies got fixed).
#
# WHY. A hook that greps the raw text blocks `grep -c "git add -A" GUARDRAILS.md`, `echo "never git
# add -A"`, a commit message quoting the rule and `gh issue list --search "git add -A"` — while
# `git -C repo add -A` slips through. Match the INVOKED command, not any substring (the class
# release-gate.sh fixed in #3/#7/#48).
#
# Order matters:
#  1. Un-quote heredoc delimiters (<<'EOF'/<<"EOF" -> <<EOF) so a REAL quoted-delimiter heredoc
#     survives the quote-strip below, while a <<EOF that lives only inside a quote or a comment does
#     NOT survive and cannot be read as an opener.
#  2. Strip quoted spans, THEN comments — quotes first so a '#' inside a string (-m "fix #43") is
#     already gone and never mis-cut as a comment (which would drop a later segment → fail OPEN).
#  3. Strip heredoc BODIES (unquoted text that quote-stripping cannot remove).
#  4. Split on ; | && || and newlines; peel leading env assignments, sudo/env, and git global options
#     (-C, -c, --git-dir, --work-tree, --namespace, --exec-path) so `FOO=1 git add -A`, `sudo git add .`
#     and `git -C repo add -A` present as `git add …` at the START of a segment.
# Here-strings (<<<) are intentionally left alone. bash 3.2 / BSD sed / POSIX awk only.
_unquote_delims() { sed -E "s/<<(-?)[[:space:]]*[\"']([A-Za-z0-9_][A-Za-z0-9_-]*)[\"']/<<\1\2/g"; }
_strip_quotes()   { sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g"; }
_strip_comments() { sed -E "s/^[[:space:]]*#.*\$//; s/([[:space:]])#.*\$/\1/"; }
_strip_heredocs() {
  awk '
    inh { t=$0; if (dash) sub(/^\t+/,"",t); if (t==delim) inh=0; next }
    {
      if (match($0, /<<-?[ \t]*[A-Za-z0-9_][A-Za-z0-9_-]*/)) {
        before=(RSTART>1)?substr($0,RSTART-1,1):""
        if (before != "<") {
          op=substr($0,RSTART,RLENGTH); dash=(op ~ /^<<-/)?1:0
          d=op; sub(/^<<-?[ \t]*/,"",d)
          delim=d; inh=1
        }
      }
      print
    }
  '
}
# normalize_segments: stdin = the raw command; stdout = one invoked segment per line, verb first.
normalize_segments() {
  _unquote_delims | _strip_quotes | _strip_comments | _strip_heredocs \
    | tr ';|&' '\n' \
    | sed -E 's/^[[:space:]]+//' \
    | sed -E 's/^(([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)[[:space:]]+)+//' \
    | sed -E 's/^(sudo|env)[[:space:]]+//' \
    | sed -E 's/^(([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)[[:space:]]+)+//' \
    | sed -E 's/^git[[:space:]]+((-C|-c|--git-dir|--work-tree|--namespace|--exec-path)([[:space:]]*=?[[:space:]]*[^[:space:]]+)?[[:space:]]+)+/git /'
}
