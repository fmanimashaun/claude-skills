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
#  1+2. `_dequote` (#1568, #1613) reads the command LEFT TO RIGHT, a line at a time, as the shell does, and rewrites each
#     word the way the shell would present it to the command. A quoted span with nothing in it a shell would act on
#     (`"-A"`, `'add'`, `"git"`, `$'\x2dA'`, a decoded `$'\x67\x69\x74'`) becomes the BARE word, so it matches a rule
#     as the plain spelling does. Any other quoted span is deleted, as before: it MENTIONS text (#906), and deleting
#     it is why `git add "x y" .` is still seen. An unquoted backslash before a character that means nothing to the
#     shell goes (`g\it`, `\-A`), and a backslash-newline joins the lines (a heredoc BODY with a quoted delimiter
#     excepted). The sed this replaces deleted `'…'` and then `"…"` by regex, so it paired quotes out of order
#     (`echo "a'b"; git add -A; echo "c'd"` lost the middle) and read a quoted word as a mention. It also un-quotes
#     a heredoc delimiter (<<'EOF' -> <<EOF) so a REAL quoted-delimiter heredoc is seen, while a <<EOF inside a quote
#     or a comment is not, and turns an arithmetic `<<` (`$((1<<2))`) into `< <` so it cannot open a heredoc.
#     An UNCLOSED double quote spans lines as it does in the shell (#1717): the lines up to the one that closes it are read as one
#     quoted span, so a `#` at the start of one of them is no comment. One that never closes is read line by line, as before, so
#     nothing after it is hidden. `$"..."` is read as `"..."` (#1718). A quoted word that is the VALUE of a git option taking one
#     (`-C "my repo"`) becomes a one-word placeholder, so the peel does not read the verb as the directory (#1709).
#     THEN comments — quotes first so a '#' inside a string (-m "fix #43") is already gone and never mis-cut as a
#     comment (which would drop a later segment → fail OPEN).
#  3. Strip heredoc BODIES (unquoted text that quote-stripping cannot remove).
#  4. Split on ; | && || ( ) and newlines, then peel what runs the real command (`_peel`): env
#     assignments; `sudo`/`env`/`command`/`exec`/`nohup`/`nice`/`time`/`timeout`/`xargs` with their
#     options; `{ ! if then elif else do while until`; git spelled `\git`, `/usr/bin/git`, `git.exe`;
#     git's global options (`-C`, `-c`, `--git-dir`, `--no-pager`, `--attr-source`, …); and an inline
#     alias (`git -c alias.p=push p` presents as `git push`). So `FOO=1 git add -A`, `sudo -u x git
#     add .`, `( git add -A )` and `git -C repo add -A` present as `git add …` at the START of a segment.
#     A leading brace list is expanded first (#1719): `{git,add,-A}` presents as `git add -A`.
#  5. #1472. A quoted span is stripped in step 2, so a command inside one was never seen:
#     `bash -c 'git add -A'`, `eval "git push --force"`, `echo "$(git add -A)"`. `_inner_strings`
#     lexes the RAW command (quotes, escapes, comments, redirects and heredoc bodies understood) and
#     prints each string a shell WILL run — the `-c` argument of sh/bash/zsh/dash/ksh, the arguments
#     of `eval`, the body of `$( )`, backticks and `<( )` — and each is normalised as a command of its
#     own, recursively (depth 3). A quote that only MENTIONS a command (`echo "bash -c 'git add -A'"`)
#     is not one of those, so it stays invisible, as #906 requires.
# KNOWN LIMITS (the threat model is an honest mistake, not obfuscation — the coordinator's ruling on
# #1470): a run-time string (`bash -c "$cmd"`, `eval "$(…)"`'s output), a script fed to a shell by
# heredoc, here-string or pipe (`bash <<EOF`, `… | bash`), an alias whose value was quoted
# (`-c alias.p='push -f'`) or defined in git config, `env -S`, and `find -exec`. And bash 3.2 (also macOS
# /bin/sh) ends a `$( )` at the first `)` inside a heredoc body, so a backtick after it RUNS there; this
# lexer follows zsh and bash 4+, which read the body as text (accepted on #1498; dev never saw it either).
# bash 3.2 / BSD sed / POSIX awk only.
_strip_comments() { sed -E "s/^[[:space:]]*#.*\$//; s/([[:space:]])#.*\$/\1/"; }
# #1526: a heredoc opened INSIDE an unclosed `$( )` (or backticks) ends where bash ends it, at the line that closes the
# `$( )`, and that line is then read as commands. Kept open to the end, it hid
# `x=$(cat <<EOF` / `foo` / `)` / `git add -A`, which bash 3.2 runs. After an early end the real delimiter
# is still PENDING, and no new heredoc opens until it is seen: otherwise a body line naming `cat <<END`
# opened a heredoc that never closed and hid the command after the substitution (#1529 review). So both
# readings stay visible, and an error here can only block, never allow.
_strip_heredocs() {
  awk '
    # A batch boundary (#1504): one string ends, and every heredoc state of it ends with it.
    $0 == "\002" { inh=0; pending=""; insub=0; inbt=0; next }
    inh {
      t=$0; sub(/\r$/,"",t); if (dash) sub(/^\t+/,"",t)
      if (t==delim) { inh=0; next }
      if (insub && $0 ~ /^[ \t]*\)/) { inh=0; pending=delim; pdash=dash; print; next }
      if (inbt && index($0, "`")) { inh=0; pending=delim; pdash=dash; print; next }
      next
    }
    pending != "" {
      t=$0; sub(/\r$/,"",t); if (pdash) sub(/^\t+/,"",t)
      if (t==pending) pending=""
      print; next
    }
    {
      if (match($0, /<<-?[ \t]*[A-Za-z0-9_][A-Za-z0-9_-]*/)) {
        before=(RSTART>1)?substr($0,RSTART-1,1):""
        if (before != "<") {
          op=substr($0,RSTART,RLENGTH); dash=(op ~ /^<<-/)?1:0
          d=op; sub(/^<<-?[ \t]*/,"",d)
          delim=d; inh=1
          head=substr($0,1,RSTART-1); opens=gsub(/\$\(/,"",head); h2=substr($0,1,RSTART-1); closes=gsub(/\)/,"",h2)
          insub=(opens>closes)?1:0
          h3=substr($0,1,RSTART-1); ticks=gsub(/`/,"",h3); inbt=(ticks%2==1)?1:0
        }
      }
      print
    }
  '
}

# Shared by `_peel` and `_inner_strings`: which leading words of a simple command are NOT the command.
# peel(t, n) returns the index of the first word that is; a wrapper's options (and the value of the
# ones that take a separate value) are stepped over, so `sudo -u deploy git` and `nice -n 5 git`
# reach `git`.
_NC_AWK_LIB='
# ANSI-C quoting, $\047...\047 (#1613), decoded as bash decodes it: \a \b \e \E \f \n \r \t \v \\\\ \047 \" \?, \nnn (octal),
# \xHH, \uHHHH, \UHHHHHHHH and \cx; any other backslash stays as written; the text is cut at a NUL, as bash cuts it.
# ansic(s, i): s[i] is the first character after the opening quote. Sets ANSIV (the decoded text), ANSIEND (the index
# just past the closing quote) and ANSIOK (0 when no closing quote follows).
function hexd(c) { return index("0123456789abcdef", tolower(c)) - 1 }
function utf8(cp) {
  if (cp < 128)   return sprintf("%c", cp)
  if (cp < 2048)  return sprintf("%c%c", 192 + int(cp / 64), 128 + cp % 64)
  if (cp < 65536) return sprintf("%c%c%c", 224 + int(cp / 4096), 128 + int(cp / 64) % 64, 128 + cp % 64)
  return sprintf("%c%c%c%c", 240 + int(cp / 262144), 128 + int(cp / 4096) % 64, 128 + int(cp / 64) % 64, 128 + cp % 64)
}
function ansic(s, i,    n, c, d, v, k, h, cp, cut, w, m) {
  n = length(s); v = ""; cut = 0
  while (i <= n) {
    c = substr(s, i, 1)
    if (c == "\047") { ANSIV = v; ANSIEND = i + 1; ANSIOK = 1; return }
    if (c != "\\") { if (!cut) v = v c; i++; continue }
    d = substr(s, i + 1, 1); i += 2; w = ""
    if (d == "") { ANSIV = v; ANSIEND = n + 1; ANSIOK = 0; return }
    m = index("abefnrtvE", d)
    if (m)                                                  w = substr("\007\010\033\014\012\015\011\013\033", m, 1)
    else if (d == "\\" || d == "\047" || d == "\"" || d == "?") w = d
    else if (d ~ /[0-7]/) {
      cp = d + 0
      for (k = 1; k < 3 && substr(s, i, 1) ~ /[0-7]/; k++) { cp = cp * 8 + substr(s, i, 1); i++ }
      cp = cp % 256
      if (cp == 0) cut = 1; else w = sprintf("%c", cp)
    }
    else if (d == "x") {
      cp = 0
      for (k = 0; k < 2 && (h = hexd(substr(s, i, 1))) >= 0; k++) { cp = cp * 16 + h; i++ }
      if (k == 0) w = "\\x"; else if (cp == 0) cut = 1; else w = sprintf("%c", cp)
    }
    else if (d == "u" || d == "U") {
      cp = 0; m = (d == "u") ? 4 : 8
      for (k = 0; k < m && (h = hexd(substr(s, i, 1))) >= 0; k++) { cp = cp * 16 + h; i++ }
      if (k == 0) w = "\\" d; else if (cp == 0) cut = 1; else w = utf8(cp)
    }
    else if (d == "c") {
      h = substr(s, i, 1)
      if (h == "" || h == "\047") w = "\\c"
      else { i++; cp = index(" !\"#$%&\047()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~", h) + 31; cp = (h == "?") ? 127 : cp % 32; if (cp == 0) cut = 1; else w = sprintf("%c", cp) }
    }
    else w = "\\" d
    if (!cut) v = v w
  }
  ANSIV = v; ANSIEND = n + 1; ANSIOK = 0
}
function skipopts(t, n, i, valued,    w, name) {
  valued = " " valued " "
  while (i <= n && t[i] ~ /^-/) {
    w = t[i]; i++
    if (w == "--") return i
    name = w; sub(/=.*/, "", name)
    if (w !~ /=/ && index(valued, " " name " ") && i <= n) i++
  }
  return i
}
function peel(t, n,    i, w) {
  i = 1
  while (i <= n) {
    w = t[i]
    if (w ~ /^[A-Za-z_][A-Za-z0-9_]*=/) { i++; continue }
    if (w == "{" || w == "!" || w == "if" || w == "then" || w == "elif" || w == "else" || w == "do" || w == "while" || w == "until") { i++; continue }
    if (w == "sudo")    { i = skipopts(t, n, i + 1, "-u -g -h -p -C -U -r -t -D -R -T --user --group --host --prompt --other-user --role --type --chdir --chroot --close-from --command-timeout"); continue }
    if (w == "env")     { i = skipopts(t, n, i + 1, "-u -C --unset --chdir"); continue }
    if (w == "command" || w == "builtin" || w == "nohup" || w == "time") { i = skipopts(t, n, i + 1, ""); continue }
    if (w == "exec")    { i = skipopts(t, n, i + 1, "-a"); continue }
    if (w == "nice")    { i = skipopts(t, n, i + 1, "-n --adjustment"); continue }
    if (w == "timeout") { i = skipopts(t, n, i + 1, "-s -k --signal --kill-after"); if (i <= n) i++; continue }
    if (w == "xargs")   { i = skipopts(t, n, i + 1, "-n -I -L -P -s -d -E -a --max-args --replace --max-lines --max-procs --max-chars --delimiter --eof --arg-file"); continue }
    break
  }
  return i
}
'

# Steps 1+2. One input line at a time, left to right, with the state a line hands the next: a heredoc owed a body, an open
# `((`. Quotes are LINE-LOCAL, as the sed they replace was: a quote with no partner on its line is an ordinary character.
# `simple(v)`: nothing in v that a shell would act on, so the quoted text is one plain word.
_dequote() {
  # LC_ALL=C: the lexer is BYTE-oriented. gawk in a UTF-8 locale makes sprintf("%c", 233) the two bytes of U+00E9, so a `$'\xe9'` or `\u00e9` decoded to
  # the wrong bytes; pinned here so the caller's locale (release-gate.sh does not pin one, the harness inherits C.UTF-8) cannot matter.
  LC_ALL=C awk "$_NC_AWK_LIB"'
  function simple(v,    k, n) {
    n = length(v); if (n == 0) return 0
    for (k = 1; k <= n; k++) if (index(BAD, substr(v, k, 1)) || substr(v, k, 1) < " ") return 0
    return 1
  }
  # The index of the closing double quote after i, a backslash skipping the next character; 0 when the line holds none.
  function dq_end(s, i,    n, c) {
    n = length(s)
    while (i <= n) { c = substr(s, i, 1); if (c == "\\") { i += 2; continue } if (c == "\"") return i; i++ }
    return 0
  }
  # One line -> OUT. Sets JOIN when the line ends in an unquoted backslash (the caller joins the next line and lexes again),
  # and appends every heredoc the line opens to NQ (committed by the caller once the line is final).
  # #1709: the word before a deleted quoted span is a git option that takes a SEPARATE value (`-C "my repo"`). Deleting the span left
  # `git -C add -A`, and the peel read `add` as the directory. A one-word placeholder keeps the operand where the shell has it.
  function optval(o) { return o ~ /(^|[ \t])(-C|-c|--git-dir|--work-tree|--namespace|--attr-source|--config-env)[ \t]+$/ }
  function lex(s,    n, i, c, d, j, k, out, w, dash, word, quoted) {
    n = length(s); i = 1; out = ""; JOIN = 0; NQN = 0; OPENDQ = 0
    while (i <= n) {
      c = substr(s, i, 1)
      if (c == "\\") {
        d = substr(s, i + 1, 1)
        if (d == "") { JOIN = 1; i++; continue }
        if (index(BAD, d)) { out = out c d; i += 2; continue }
        out = out d; i += 2; continue
      }
      if (c == "\047") {
        j = index(substr(s, i + 1), "\047")
        if (j == 0) { out = out c; i++; continue }
        w = substr(s, i + 1, j - 1); if (simple(w)) out = out w; else if (optval(out)) out = out "_"
        i += j + 1; continue
      }
      # #1718: `$"..."` is read like `"..."` (the locale lookup falls back to the text), so the `$` goes and the span is lexed as an ordinary one.
      if (c == "$" && substr(s, i + 1, 1) == "\"") { i++; continue }
      if (c == "\"") {
        j = dq_end(s, i + 1)
        # #1717: an UNCLOSED double quote spans lines in the shell. The caller joins the following lines until one closes it (LEG: it never did, so the
        # old reading stands: the quote is an ordinary character and the rest of the line stays visible, which can only block).
        if (j == 0) { if (!LEG) { OPENDQ = 1; return } out = out c; i++; continue }
        w = substr(s, i + 1, j - i - 1); if (simple(w)) out = out w; else if (optval(out)) out = out "_"
        i = j + 1; continue
      }
      if (c == "$" && substr(s, i + 1, 1) == "\047") {
        ansic(s, i + 2)
        if (!ANSIOK) { out = out c; i++; continue }
        if (simple(ANSIV)) out = out ANSIV; else if (optval(out)) out = out "_"
        i = ANSIEND; continue
      }
      if (c == "#" && (i == 1 || substr(s, i - 1, 1) == " " || substr(s, i - 1, 1) == "\t")) { out = out substr(s, i); break }
      if (c == "(") {
        if (AR > 0) AR++
        else if (substr(s, i + 1, 1) == "(") { AR = 2; out = out "(("; i += 2; continue }
        out = out c; i++; continue
      }
      if (c == ")") { if (AR > 0) AR--; out = out c; i++; continue }
      if (c == "<" && substr(s, i, 2) == "<<" && substr(s, i + 2, 1) != "<" && (i == 1 || substr(s, i - 1, 1) != "<")) {
        if (AR > 0) { out = out "< <"; i += 2; continue }
        j = i + 2; dash = 0
        if (substr(s, j, 1) == "-") { dash = 1; j++ }
        while (substr(s, j, 1) == " " || substr(s, j, 1) == "\t") j++
        word = ""; quoted = 0
        while (j <= n) {
          d = substr(s, j, 1)
          if (d == " " || d == "\t" || d == ";" || d == "&" || d == "|" || d == "(" || d == ")" || d == "<" || d == ">") break
          if (d == "\047") { k = index(substr(s, j + 1), "\047"); if (k == 0) break; word = word substr(s, j + 1, k - 1); quoted = 1; j += k + 1; continue }
          if (d == "\"") { k = dq_end(s, j + 1); if (k == 0) break; word = word substr(s, j + 1, k - j - 1); quoted = 1; j = k + 1; continue }
          if (d == "\\") { word = word substr(s, j + 1, 1); quoted = 1; j += 2; continue }
          word = word d; j++
        }
        if (word ~ /^[A-Za-z0-9_][A-Za-z0-9_-]*$/) {
          out = out "<<" (dash ? "-" : "") word
          NQN++; NQW[NQN] = word; NQD[NQN] = dash; NQQ[NQN] = quoted
          i = j; continue
        }
      }
      out = out c; i++
    }
    OUT = out
  }
  function reset() { INB = 0; QN = 0; QI = 0; BUF = ""; ACC = ""; AR = 0; DQN = 0; AR0 = 0 }
  # One finished logical line: lex it, print it, and commit the heredocs it opens. An unclosed double quote (#1717) holds it back instead:
  # DQL[1..DQN] are the lines read since the quote opened, joined and lexed again by `step` once one of them closes it.
  function process(raw) {
    AR0 = AR; lex(raw)
    if (JOIN) { BUF = substr(raw, 1, length(raw) - 1); return }
    if (OPENDQ && !LEG) { BUF = ""; DQN = 1; DQL[1] = raw; return }
    BUF = ""
    print OUT
    if (NQN) { for (k = 1; k <= NQN; k++) { QN++; QW[QN] = NQW[k]; QD[QN] = NQD[k]; QQ[QN] = NQQ[k] } QI = 1; INB = 1 }
  }
  function step(line,    t, raw, k) {
    if (INB) {
      # A heredoc body is not lexed. An UNQUOTED delimiter lets a backslash-newline join the body lines, as it does in bash (an odd run of
      # backslashes is judged by the character before the last, which is enough for a body line), and
      # the terminator is compared after the join; a quoted delimiter joins nothing. A CR is part of both words in bash.
      if (!QQ[QI] && line ~ /\\$/ && substr(line, length(line) - 1, 1) != "\\") { ACC = ACC substr(line, 1, length(line) - 1); return }
      line = ACC line; ACC = ""
      t = line; sub(/\r$/, "", t); if (QD[QI]) sub(/^\t+/, "", t)
      print line
      if (t == QW[QI]) { QI++; if (QI > QN) { INB = 0; QN = 0; QI = 0 } }
      return
    }
    if (DQN > 0 && !LEG) {
      # Cost: a line that does not close the quote is only stored, so a long unclosed quote is not lexed again for every line it holds.
      if (dq_end(line, 1) == 0) { DQL[++DQN] = line; return }
      raw = DQL[1]; for (k = 2; k <= DQN; k++) raw = raw "\n" DQL[k]
      raw = raw "\n" line; DQN = 0; AR = AR0
      process(raw); return
    }
    process(BUF line)
  }
  # The quote never closed (the end of the input, or a batch boundary): read those lines one at a time, as before #1717.
  function flushdq(    n, k, held) {
    if (DQN == 0) return
    n = DQN; DQN = 0; LEG = 1; AR = AR0
    for (k = 1; k <= n; k++) held[k] = DQL[k]
    for (k = 1; k <= n; k++) step(held[k])
    LEG = 0
  }
  # A batch boundary (#1504): one string ends, and every state of it ends with it.
  $0 == "\002" { flushdq(); reset(); print; next }
  { step($0) }
  END { flushdq(); if (BUF != "") { lex(BUF); print OUT } }
  BEGIN { BAD = ";|&()<>$`\"\\# \t\n\r\f\v\047"; reset() }
  '
}

# Step 4's peel, one segment per line. git's global options were measured against git 2.50.1:
# `-C -c --git-dir --work-tree --namespace --attr-source --config-env` take a separate value;
# every other leading option (`--no-pager`, `-P`, `--exec-path`, …) is a flag.
_peel() {
  awk "$_NC_AWK_LIB"'
  function isgit(w) { sub(/^\\/, "", w); return w ~ /^([^ \t]*\/)?git(\.exe)?$/ }
  {
    n = split($0, t, " ")
    i = peel(t, n)
    # #1719: the shell expands a leading brace list into words BEFORE it runs anything: `{git,add,-A}` runs `git add -A`. Expanded here, then the peel is
    # read again, so `{sudo,git,add,.}` is seen too. Only a list of plain words with a comma (`{a,b}`; not `{`, `{ x; }` or `{1..3}`) is expanded.
    if (i <= n && t[i] ~ /^\{[^{}]*,[^{}]*\}$/) {
      m = split(substr(t[i], 2, length(t[i]) - 2), bw, ",")
      split("", t2); k = 0
      for (j = 1; j < i; j++) t2[++k] = t[j]
      for (j = 1; j <= m; j++) if (bw[j] != "") t2[++k] = bw[j]
      for (j = i + 1; j <= n; j++) t2[++k] = t[j]
      split("", t); for (j = 1; j <= k; j++) t[j] = t2[j]
      n = k; i = peel(t, n)
    }
    if (i <= n) { w = t[i]; sub(/^\\/, "", w); t[i] = w }
    if (i <= n && isgit(t[i])) {
      split("", al); j = i + 1
      while (j <= n && t[j] ~ /^-/) {
        w = t[j]; j++
        if (w ~ /=/) continue
        if (w == "-C" || w == "-c" || w == "--git-dir" || w == "--work-tree" || w == "--namespace" || w == "--attr-source" || w == "--config-env") {
          if (w == "-c" && j <= n && tolower(t[j]) ~ /^alias\.[^=]+=./) {
            a = t[j]; sub(/^[^.]*\./, "", a); v = a; sub(/^[^=]*=/, "", v); sub(/=.*/, "", a); al[tolower(a)] = v
          }
          j++
        }
      }
      out = "git"
      if (j <= n) { w = t[j]; if (tolower(w) in al) w = al[tolower(w)]; out = out " " w; j++ }
      for (; j <= n; j++) out = out " " t[j]
      print out; next
    }
    out = ""
    for (j = i; j <= n; j++) out = out (j > i ? " " : "") t[j]
    print out
  }
  '
}

# Step 5. One string per line, its own newlines carried as \001 so a multi-line string survives.
_inner_strings() {
  LC_ALL=C awk -v batch="${1:-0}" "$_NC_AWK_LIB"'
  function emit(v) { if (SKIP) return; gsub(/\n/, "\001", v); print v }
  function bt_end(s, i,    n, c) {
    n = length(s)
    while (i <= n) { c = substr(s, i, 1); if (c == "\\") { i += 2; continue } if (c == "`") return i; i++ }
    return n + 1
  }
  function dquote(s, i,    n, c, d, j, v) {
    n = length(s); v = ""
    while (i <= n) {
      c = substr(s, i, 1)
      if (c == "\"") { DQV = v; return i + 1 }
      if (c == "\\") {
        d = substr(s, i + 1, 1)
        if (d == "$" || d == "`" || d == "\"" || d == "\\") { v = v d; i += 2; continue }
        if (d == "\n") { i += 2; continue }
        v = v c; i++; continue
      }
      if (c == "$" && substr(s, i + 1, 1) == "(") { j = subst_end(s, i + 2); emit(substr(s, i + 2, j - i - 2)); v = v substr(s, i, j - i + 1); i = j + 1; continue }
      if (c == "`") { j = bt_end(s, i + 1); emit(substr(s, i + 1, j - i - 1)); v = v substr(s, i, j - i + 1); i = j + 1; continue }
      v = v c; i++
    }
    DQV = v; return n + 1
  }
  # i is just past "$(" (or "<("); returns the index of the matching ")". Nothing inside is emitted
  # here: the body is emitted whole by the caller and lexed again on its own. A heredoc BODY inside
  # is skipped, so a `)` in it -- `1) do not run ...` in a PR body -- cannot end the substitution.
  function subst_end(s, i,    n, c, depth, j, hn, hd, ht, d, e, line, k, start, found) {
    n = length(s); depth = 1; SKIP++; hn = 0
    while (i <= n) {
      c = substr(s, i, 1)
      if (c == "\\") { i += 2; continue }
      if (c == "<" && substr(s, i, 2) == "<<" && substr(s, i + 2, 1) != "<") {
        i += 2; hn++; ht[hn] = 0
        if (substr(s, i, 1) == "-") { ht[hn] = 1; i++ }
        while (substr(s, i, 1) == " " || substr(s, i, 1) == "\t") i++
        d = ""
        while (i <= n) {
          c = substr(s, i, 1)
          if (c == " " || c == "\t" || c == "\n" || c == ";" || c == "&" || c == "|" || c == "(" || c == ")" || c == "<" || c == ">") break
          if (c != "\047" && c != "\"" && c != "\\") d = d c
          i++
        }
        hd[hn] = d; continue
      }
      if (c == "\n" && hn) {
        i++; start = i; found = 1
        for (k = 1; k <= hn && found; k++) {
          found = 0
          while (i <= n) {
            e = index(substr(s, i), "\n"); if (e == 0) e = n - i + 2
            line = substr(s, i, e - 1); i += e
            if (ht[k]) sub(/^\t+/, "", line)
            if (line == hd[k]) { found = 1; break }
          }
        }
        # A heredoc that never closes would hide everything after it: lex that text as before instead.
        if (!found) i = start
        hn = 0; continue
      }
      if (c == "\047") { j = index(substr(s, i + 1), "\047"); if (j == 0) break; i += j + 1; continue }
      if (c == "\"") { i = dquote(s, i + 1); continue }
      if (c == "`") { i = bt_end(s, i + 1) + 1; continue }
      if (c == "(") depth++
      if (c == ")") { depth--; if (depth == 0) { SKIP--; return i } }
      i++
    }
    SKIP--; return n + 1
  }
  function endword() {
    if (!HAS) return
    if (HD) { HDN++; HDD[HDN] = W; HDT[HDN] = HDASH; HD = 0 }
    else if (REDIR) REDIR = 0
    else WORDS[++NW] = W
    W = ""; HAS = 0
  }
  function endcmd(    k, b, j, w, seenc, v) {
    endword()
    k = peel(WORDS, NW)
    if (k <= NW) {
      b = WORDS[k]; sub(/^\\/, "", b); sub(/.*\//, "", b)
      if (b == "eval") {
        v = ""; for (j = k + 1; j <= NW; j++) v = v (j > k + 1 ? " " : "") WORDS[j]
        if (v != "") emit(v)
      } else if (b ~ /^(sh|bash|zsh|dash|ksh|ash|mksh)(\.exe)?$/) {
        seenc = 0
        for (j = k + 1; j <= NW; j++) {
          w = WORDS[j]
          if (w == "--") { if (seenc && j < NW) emit(WORDS[j + 1]); break }
          if (w ~ /^[-+]./) {
            if (w ~ /^-[A-Za-z]*c/) seenc = 1
            if (w ~ /^[-+][oO]$/ || w == "--rcfile" || w == "--init-file") j++
            continue
          }
          if (seenc) emit(w)
          break
        }
      }
    }
    split("", WORDS); NW = 0; REDIR = 0
  }
  { S = S (NR > 1 ? "\n" : "") $0 }
  # One piece of a batch (#1504): every string the previous depth emitted is lexed on its own.
  function lex(s,    n, i, c, d, j, k, e, line) {
    n = length(s); i = 1; W = ""; HAS = 0; NW = 0; HDN = 0; SKIP = 0; REDIR = 0; HD = 0
    split("", WORDS)
    while (i <= n) {
      c = substr(s, i, 1)
      if (c == "\\") { d = substr(s, i + 1, 1); if (d != "\n" && d != "") { W = W d; HAS = 1 } i += 2; continue }
      if (c == "\047") { j = index(substr(s, i + 1), "\047"); if (j == 0) break; W = W substr(s, i + 1, j - 1); HAS = 1; i += j + 1; continue }
      if (c == "$" && substr(s, i + 1, 1) == "\"") { i++; continue }
      if (c == "$" && substr(s, i + 1, 1) == "\047") { ansic(s, i + 2); W = W ANSIV; HAS = 1; i = ANSIEND; continue }
      if (c == "\"") { i = dquote(s, i + 1); W = W DQV; HAS = 1; continue }
      if (c == "$" && substr(s, i + 1, 1) == "(") { j = subst_end(s, i + 2); emit(substr(s, i + 2, j - i - 2)); W = W substr(s, i, j - i + 1); HAS = 1; i = j + 1; continue }
      if (c == "`") { j = bt_end(s, i + 1); emit(substr(s, i + 1, j - i - 1)); W = W substr(s, i, j - i + 1); HAS = 1; i = j + 1; continue }
      if (c == "#" && !HAS) { while (i <= n && substr(s, i, 1) != "\n") i++; continue }
      if (c == " " || c == "\t") { endword(); i++; continue }
      if (c == "\n") {
        endcmd(); i++
        for (k = 1; k <= HDN; k++) {
          while (i <= n) {
            e = index(substr(s, i), "\n"); if (e == 0) e = n - i + 2
            line = substr(s, i, e - 1); i += e
            if (HDT[k]) sub(/^\t+/, "", line)
            if (line == HDD[k]) break
          }
        }
        HDN = 0; continue
      }
      if (c == ";" || c == "&" || c == "|" || c == "(" || c == ")") { endcmd(); i++; continue }
      if (c == "<" || c == ">") {
        if (W ~ /^[0-9]*$/) { W = ""; HAS = 0 } else endword()
        if ((substr(s, i + 1, 1) == "(") ) { j = subst_end(s, i + 2); emit(substr(s, i + 2, j - i - 2)); i = j + 1; continue }
        if (substr(s, i, 3) == "<<<") { i += 3; REDIR = 1; continue }
        if (substr(s, i, 2) == "<<") { i += 2; HDASH = 0; if (substr(s, i, 1) == "-") { HDASH = 1; i++ } HD = 1; continue }
        i++
        while (i <= n && (substr(s, i, 1) == ">" || substr(s, i, 1) == "&" || substr(s, i, 1) == "<")) i++
        if (c == ">" && substr(s, i, 1) == "|") i++
        REDIR = 1; continue
      }
      W = W c; HAS = 1; i++
    }
    endcmd()
  }
  END {
    # Cost: the lexer walks the text a character at a time, so skip it when nothing it looks for is
    # there. Judged with quotes and backslashes removed, because the lexer dequotes words before it
    # matches them (`e'v'al`, `bas\h -c`; #1498 review). gsub, not a bash pattern substitution: that
    # is superlinear on bash 3.2 and made an 8 KB PR body cost 32 s in guard-bash (#1504).
    p = S; gsub(/[\047"\\]/, "", p)
    if (p !~ /\$\(|`|<\(|eval|sh/) exit
    # Only a BATCH (depth > 0) is split: a raw command holding a \002 line must not be cut mid-string
    # (#1519 review). _join_strings removes \002 from every string, so content never fakes a boundary.
    if (batch) np = split(S, P, "\n\002\n"); else { np = 1; P[1] = S }
    for (pi = 1; pi <= np; pi++) lex(P[pi])
  }
  '
}

# One string per line from _inner_strings ( \001 = its own newlines) -> the strings, joined by a line
# holding only \002, which _strip_heredocs and the lexer both treat as a hard reset.
_join_strings() { awk 'NR > 1 { print "\002" } { gsub(/\002/, ""); gsub(/\001/, "\n"); print }'; }

_normalize_one() {
  _dequote | _strip_comments | _strip_heredocs \
    | tr ';|&()' '\n' \
    | _peel
}

# normalize_segments: stdin = the raw command; stdout = one invoked segment per line, verb first.
# The raw text is read with a BUILTIN, never `cat`: a missing binary must not empty the command.
# #1504: the strings each depth emits are normalised in ONE pipeline (joined by _join_strings), not one
# pipeline per string -- 50 `$(…)` cost 50 pipelines before. Depth 3, as before.
normalize_segments() {
  local raw="" level next d=0
  IFS= read -r -d '' raw || true
  # Every status is RETURNED (#1529 review): discarded, an awk that failed read as a clean, empty result.
  printf '%s' "$raw" | _normalize_one || return 1
  level="$raw"
  while [ "$d" -lt 3 ]; do
    next="$(printf '%s' "$level" | _inner_strings "$(( d > 0 ))" | _join_strings)" || return 1
    [ -n "$next" ] || return 0
    printf '%s\n' "$next" | _normalize_one || return 1
    level="$next"; d=$((d + 1))
  done
}
