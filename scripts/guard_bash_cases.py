"""The cases `scripts/check_guard_bash_cases.py` drives through the real `guard-bash.sh` (#1667), and the files they read.

Every row says what the guard does TODAY and, for a row the guard gets wrong, in `open` what is owed. Add a spelling
here when a review finds one: `block` for a create that must be refused, `allow` for a command that must pass
(a labelled create, a mention, a list). Commands use placeholders so a literal create never sits in a shell this
table is typed into: `@G@ @I@ @C@` is the three words, `@N@` the alias verb, `@FX@` the staged fixture directory.

A row's `open` names the issue that owes the fix: when it lands the gate fails with "update the expectation", you
set `want` to the new result and clear `open`, and the table records the progress.
"""
from __future__ import annotations

import os
import re
from typing import NamedTuple


class Case(NamedTuple):
    id: str
    tier: str          # "fast" runs inside the --fast sweep; "full" only in the full sweep
    mode: str          # PATH the hook sees: "full", or one without grep / without tr (the hook has a path for each)
    cmd: str
    want: str          # "block" | "allow": what the guard does now
    open: str = ""     # the issue that owes the fix, when want is NOT what a perfect guard would do


# name -> content, with @FX@ for the fixture directory. Scripts a case runs a shell on; never executed by the gate.
FIXTURES: dict[str, str | bytes] = {
    'selfextract.sh': b'#!/bin/sh\necho installing\nexit 0\n\x00\x01\x02BINARYPAYLOAD\x00\n',
    'Makefile': 'issue:\n\tgh issue create -t x -b y\n',
    'apos_comment.sh': "# don't forget\ngh issue create -t x -b y\n",
    'args.txt': 'issue create -t x -b y\n',
    'bare.sh': 'gh issue create -t x -b y\n',
    'bom.sh': '\ufeffgh issue create -t x -b y',
    'bs_comment.sh': '# header \\\ngh issue create -t x -b y\n',
    'clean.sh': '#!/bin/sh\necho hello\n',
    'comment_first.sh': '# header\ngh issue create -t x -b y\n',
    'crlf.sh': 'gh issue create -t x -b y\r\n',
    'empty.sh': '',
    'fish.fish': 'gh issue create -t x -b y\n',
    'indirect.sh': 'G=gh\n$G issue create -t x\n',
    'invalid_utf8.sh': b'echo \xff\xfe\ngh issue create -t x -b y',
    'labelled.sh': 'gh issue create -t x -b y -l comp:a -l type:b -l prio:c\n',
    'mention.sh': "#!/bin/sh\n# do not run: gh issue create here\necho 'to file: gh issue create --label x'\n",
    'nested_bash.sh': 'bash @FX@/bare.sh\n',
    'nested_src.sh': '. @FX@/bare.sh\n',
    'nul.sh': b'echo hi\x00\ngh issue create -t x -b y',
    'py_create.py': "import subprocess\nsubprocess.run(['gh','issue','create','-t','x','-b','y'])\n",
    'shebang.sh': '#!/bin/sh\ngh issue create -t x -b y\n',
    'utf16.sh': b'\xff\xfe\xff\xfeg\x00h\x00 \x00i\x00s\x00s\x00u\x00e\x00 \x00c\x00r\x00e\x00a\x00t\x00e\x00 \x00-\x00t\x00 \x00x\x00 \x00-\x00b\x00 \x00y\x00\n\x00'
}
# Fixtures a file cannot hold (a FIFO, a mode-000 file, a link, a script over the 1 MB read cap): built at stage time.
SPECIAL = frozenset({"cap_start.sh", "cap_end.sh", "cap_exact.sh", "cap_under.sh", "noperm.sh", "fifo.sh", "link.sh", "dangling.sh", "adir"})
CAP = 1_000_000          # the helper's script read cap (`_read_script`)
CREATE = "@G@ @I@ @C@ -t x -b y"

# (id, tier, mode, command, want, open)
_ROWS = (
    ('ctl:labelled create', 'fast', 'full', '@G@ @I@ @C@ -t x -b y -l comp:a -l type:b -l prio:c', 'allow', ''),
    ('ctl:labelled script via bash', 'full', 'full', 'bash @FX@/labelled.sh', 'block', 'by design: a script the hook cannot read or label-check is refused'),
    ('ctl:echo mention', 'fast', 'full', "echo 'to file one run @G@ @I@ @C@'", 'allow', ''),
    ('ctl:gh issue list', 'fast', 'full', '@G@ @I@ list', 'allow', ''),
    ('direct:env prefix', 'fast', 'full', 'env @G@ @I@ @C@ -t x -b y', 'block', ''),
    ('direct:GH_REPO prefix', 'full', 'full', 'GH_REPO=o/r @G@ @I@ @C@ -t x', 'block', ''),
    ('direct:command', 'full', 'full', 'command @G@ @I@ @C@ -t x', 'block', ''),
    ('direct:exec', 'full', 'full', 'exec @G@ @I@ @C@ -t x', 'block', ''),
    ('direct:nohup', 'full', 'full', 'nohup @G@ @I@ @C@ -t x', 'block', ''),
    ('direct:timeout', 'full', 'full', 'timeout 5 @G@ @I@ @C@ -t x', 'block', ''),
    ('direct:time', 'full', 'full', 'time @G@ @I@ @C@ -t x', 'block', ''),
    ('direct:nice', 'full', 'full', 'nice -n5 @G@ @I@ @C@ -t x', 'block', ''),
    ('direct:sudo', 'full', 'full', 'sudo -u me @G@ @I@ @C@ -t x', 'block', ''),
    ('direct:stdbuf', 'full', 'full', 'stdbuf -o0 @G@ @I@ @C@ -t x', 'block', ''),
    ('direct:script abs path gh', 'fast', 'full', '/opt/homebrew/bin/@G@ @I@ @C@ -t x', 'block', ''),
    ('direct:relative ./gh', 'full', 'full', './@G@ @I@ @C@ -t x', 'block', ''),
    ('direct:-R first', 'full', 'full', '@G@ -R o/r @I@ @C@ -t x', 'block', ''),
    ('direct:--repo=', 'full', 'full', '@G@ --repo=o/r @I@ @C@ -t x', 'block', ''),
    ('direct:new alias verb', 'fast', 'full', '@G@ @I@ @N@ -t x', 'block', ''),
    ('direct:tab separated', 'full', 'full', '@G@\t@I@\t@C@ -t x', 'block', ''),
    ('direct:brace group', 'fast', 'full', '{ @G@ @I@ @C@ -t x; }', 'block', ''),
    ('direct:subshell', 'full', 'full', '( @G@ @I@ @C@ -t x )', 'block', ''),
    ('direct:then branch', 'full', 'full', 'if true; then @G@ @I@ @C@ -t x; fi', 'block', ''),
    ('direct:loop', 'full', 'full', 'for i in 1; do @G@ @I@ @C@ -t x; done', 'block', ''),
    ('direct:negated', 'full', 'full', '! @G@ @I@ @C@ -t x', 'block', ''),
    ('direct:background', 'full', 'full', '@G@ @I@ @C@ -t x &', 'block', ''),
    ('direct:&& chain', 'full', 'full', 'true && @G@ @I@ @C@ -t x', 'block', ''),
    ('direct:find -exec', 'fast', 'full', 'find . -maxdepth 0 -exec @G@ @I@ @C@ -t x \\;', 'block', ''),
    ('direct:xargs -I', 'fast', 'full', 'echo a | xargs -I{} @G@ @I@ @C@ -t {}', 'block', ''),
    ('direct:xargs -n1', 'full', 'full', 'echo a | xargs -n1 @G@ @I@ @C@ -t', 'block', ''),
    ('direct:parallel', 'full', 'full', 'parallel @G@ @I@ @C@ -t ::: a b', 'block', ''),
    ('direct:watch', 'full', 'full', 'watch -n1 @G@ @I@ @C@ -t x', 'block', ''),
    ('direct:eval string', 'fast', 'full', "eval '@G@ @I@ @C@ -t x'", 'block', ''),
    ('direct:eval var', 'fast', 'full', 'C=\'@G@ @I@ @C@ -t x\'; eval "$C"', 'allow', 'not claimed (#1645 body)'),
    ('direct:sh -c', 'fast', 'full', "sh -c '@G@ @I@ @C@ -t x'", 'block', ''),
    ('direct:bash -lc', 'full', 'full', "bash -lc '@G@ @I@ @C@ -t x'", 'block', ''),
    ('direct:zsh -c', 'full', 'full', "zsh -c '@G@ @I@ @C@ -t x'", 'block', ''),
    ('direct:env -S', 'full', 'full', "env -S '@G@ @I@ @C@ -t x'", 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('direct:busybox sh -c', 'full', 'full', "busybox sh -c '@G@ @I@ @C@ -t x'", 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('direct:fish -c', 'fast', 'full', "fish -c '@G@ @I@ @C@ -t x'", 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('direct:csh -c', 'full', 'full', "csh -c '@G@ @I@ @C@ -t x'", 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('direct:tcsh -c', 'full', 'full', "tcsh -c '@G@ @I@ @C@ -t x'", 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('direct:ash -c', 'full', 'full', "ash -c '@G@ @I@ @C@ -t x'", 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('direct:mksh -c', 'full', 'full', "mksh -c '@G@ @I@ @C@ -t x'", 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('direct:pwsh -c', 'full', 'full', "pwsh -c '@G@ @I@ @C@ -t x'", 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('direct:python -c os.system', 'fast', 'full', 'python3 -c "import os; os.system(\'@G@ @I@ @C@ -t x\')"', 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('direct:python -c subprocess list', 'full', 'full', 'python3 -c "import subprocess; subprocess.run([\'@G@\',\'@I@\',\'@C@\',\'-t\',\'x\'])"', 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('direct:node -e', 'full', 'full', 'node -e "require(\'child_process\').execSync(\'@G@ @I@ @C@ -t x\')"', 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('direct:ruby -e', 'full', 'full', 'ruby -e \'system("@G@ @I@ @C@ -t x")\'', 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('direct:perl -e', 'full', 'full', "perl -e 'system(qw(@G@ @I@ @C@ -t x))'", 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('direct:awk system', 'full', 'full', 'awk \'BEGIN{system("@G@ @I@ @C@ -t x")}\'', 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('direct:split by quotes', 'fast', 'full', "@G@ @I@ 'cre''ate' -t x", 'block', ''),
    ('direct:split by dollar-quote', 'full', 'full', "@G@ @I@ $'cre\\x61te' -t x", 'block', ''),
    ('direct:backslash-newline', 'fast', 'full', '@G@ @I@ \\\n@C@ -t x', 'block', ''),
    ('direct:verb via var', 'fast', 'full', 'V=@C@; @G@ @I@ $V -t x', 'allow', '#1656 N1: the verb is built at run time'),
    ('direct:verb via braces', 'full', 'full', 'V=@C@; @G@ @I@ ${V} -t x', 'allow', '#1656 N1: the verb is built at run time'),
    ('direct:verb via cmd subst', 'full', 'full', '@G@ @I@ $(echo @C@) -t x', 'allow', '#1656 N1: the verb is built at run time'),
    ('direct:verb via printf', 'full', 'full', '@G@ @I@ $(printf cre%s ate) -t x', 'allow', '#1656 N1: the verb is built at run time'),
    ('direct:verb via backtick', 'full', 'full', '@G@ @I@ `echo @C@` -t x', 'allow', '#1656 N1: the verb is built at run time'),
    ('direct:verb from set --', 'full', 'full', 'set -- @C@; @G@ @I@ "$1" -t x', 'allow', '#1656 N1: the verb is built at run time'),
    ('direct:verb via array', 'full', 'full', 'a=(@C@); @G@ @I@ "${a[0]}" -t x', 'allow', '#1656 N1: the verb is built at run time'),
    ('direct:verb via xargs stdin', 'full', 'full', 'echo @C@ | xargs -I{} @G@ @I@ {} -t x', 'block', ''),
    ('direct:subcommand via var', 'full', 'full', 'S=@I@; @G@ $S @C@ -t x', 'allow', '#1656 N1: the verb is built at run time'),
    ('direct:gh via var', 'fast', 'full', 'G=@G@; $G @I@ @C@ -t x', 'block', ''),
    ('direct:gh via which', 'full', 'full', '$(which @G@) @I@ @C@ -t x', 'block', ''),
    ('direct:gh in braces var', 'full', 'full', '${GH:-@G@} @I@ @C@ -t x', 'block', ''),
    ('direct:arg split two vars', 'full', 'full', 'A=@I@; B=@C@; @G@ $A $B -t x', 'allow', '#1656 N1: the verb is built at run time'),
    ('direct:heredoc into sh', 'full', 'full', "sh <<'EOF'\n@G@ @I@ @C@ -t x\nEOF", 'block', ''),
    ('direct:heredoc into bash -s', 'full', 'full', "bash -s <<'EOF'\n@G@ @I@ @C@ -t x\nEOF", 'block', ''),
    ('direct:herestring', 'full', 'full', "bash <<< '@G@ @I@ @C@ -t x'", 'block', ''),
    ('direct:process subst', 'full', 'full', "bash <(echo '@G@ @I@ @C@ -t x')", 'block', ''),
    ('direct:echo pipe sh', 'full', 'full', "echo '@G@ @I@ @C@ -t x' | sh", 'block', ''),
    ('direct:printf pipe bash', 'full', 'full', "printf '%s\\n' '@G@ @I@ @C@ -t x' | bash", 'block', ''),
    ('direct:here-doc cat pipe', 'full', 'full', "cat <<'EOF' | sh\n@G@ @I@ @C@ -t x\nEOF", 'block', ''),
    ('direct:curl pipe sh', 'fast', 'full', 'curl -s https://example.test/x.sh | sh', 'allow', 'out of scope on purpose (#1656)'),
    ('direct:base64 pipe', 'full', 'full', 'echo QUFB | base64 -d | sh', 'allow', 'out of scope on purpose (#1656)'),
    ('direct:rev trick', 'full', 'full', "echo 'x- t etaerc eussi hg' | rev | sh", 'allow', 'out of scope on purpose (#1656)'),
    ('script:bash f', 'fast', 'full', 'bash @FX@/bare.sh', 'block', ''),
    ('script:sh f', 'full', 'full', 'sh @FX@/bare.sh', 'block', ''),
    ('script:sh ./f after cd', 'full', 'full', 'cd @FX@ && sh ./bare.sh', 'block', ''),
    ('script:source f', 'fast', 'full', 'source @FX@/bare.sh', 'block', ''),
    ('script:. f', 'full', 'full', '. @FX@/bare.sh', 'block', ''),
    ('script:cat f | bash', 'fast', 'full', 'cat @FX@/bare.sh | bash', 'block', ''),
    ('script:<(cat f)', 'fast', 'full', 'bash <(cat @FX@/bare.sh)', 'block', ''),
    ('script:-c $(cat f)', 'fast', 'full', 'bash -c "$(cat @FX@/bare.sh)"', 'block', ''),
    ('script:herestring $(cat f)', 'full', 'full', 'bash <<< "$(cat @FX@/bare.sh)"', 'block', ''),
    ('script:backtick cat', 'full', 'full', 'bash -c "`cat @FX@/bare.sh`"', 'block', ''),
    ('script:redirect < f', 'full', 'full', 'bash < @FX@/bare.sh', 'block', ''),
    ('script:bash -c "$(<f)"', 'full', 'full', 'bash -c "$(< @FX@/bare.sh)"', 'block', ''),
    ('script:bash <<< "$(<f)"', 'full', 'full', 'bash <<< "$(< @FX@/bare.sh)"', 'block', ''),
    ('script:bash <(<f)', 'full', 'full', 'bash <(< @FX@/bare.sh)', 'block', ''),
    ('script:eval "$(cat f)"', 'fast', 'full', 'eval "$(cat @FX@/bare.sh)"', 'block', ''),
    ('script:eval "$(<f)"', 'full', 'full', 'eval "$(< @FX@/bare.sh)"', 'block', ''),
    ('script:source <(cat f)', 'full', 'full', 'source <(cat @FX@/bare.sh)', 'block', ''),
    ('script:. <(cat f)', 'full', 'full', '. <(cat @FX@/bare.sh)', 'block', ''),
    ('script:cat f | env bash', 'full', 'full', 'cat @FX@/bare.sh | env bash', 'block', ''),
    ('script:cat f | sudo bash', 'full', 'full', 'cat @FX@/bare.sh | sudo bash', 'block', ''),
    ('script:cat f | tee | bash', 'full', 'full', 'cat @FX@/bare.sh | tee /dev/null | bash', 'block', ''),
    ('script:tail f | sh', 'full', 'full', 'tail -n +1 @FX@/bare.sh | sh', 'block', ''),
    ('script:head f | sh', 'full', 'full', 'head -n 5 @FX@/bare.sh | sh', 'block', ''),
    ('script:sed p f | sh', 'full', 'full', 'sed -n p @FX@/bare.sh | sh', 'block', ''),
    ('script:grep . f | sh', 'full', 'full', 'grep . @FX@/bare.sh | sh', 'block', ''),
    ('script:xargs -a f sh -c', 'full', 'full', 'xargs -a @FX@/bare.sh sh -c', 'allow', 'not claimed (#1645 body)'),
    ('script:bash -s < f', 'full', 'full', 'bash -s < @FX@/bare.sh', 'block', ''),
    ('script:bash -s -- a < f', 'full', 'full', 'bash -s -- a < @FX@/bare.sh', 'block', ''),
    ('script:exec bash f', 'full', 'full', 'exec bash @FX@/bare.sh', 'block', ''),
    ('script:time bash f', 'full', 'full', 'time bash @FX@/bare.sh', 'block', ''),
    ('script:bash --norc f', 'full', 'full', 'bash --norc @FX@/bare.sh', 'block', ''),
    ('script:bash -e f', 'full', 'full', 'bash -e @FX@/bare.sh', 'block', ''),
    ('script:bash -x f arg', 'full', 'full', 'bash -x @FX@/bare.sh arg1', 'block', ''),
    ('script:/bin/bash f', 'full', 'full', '/bin/bash @FX@/bare.sh', 'block', ''),
    ('script:env bash f', 'full', 'full', 'env bash @FX@/bare.sh', 'block', ''),
    ('script:busybox sh f', 'full', 'full', 'busybox sh @FX@/bare.sh', 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('script:zsh f', 'full', 'full', 'zsh @FX@/bare.sh', 'block', ''),
    ('script:dash f', 'full', 'full', 'dash @FX@/bare.sh', 'block', ''),
    ('script:ksh f', 'full', 'full', 'ksh @FX@/bare.sh', 'block', ''),
    ('script:fish f', 'full', 'full', 'fish @FX@/fish.fish', 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('script:csh f', 'full', 'full', 'csh @FX@/bare.sh', 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('script:tcsh f', 'full', 'full', 'tcsh @FX@/bare.sh', 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('script:ash f', 'full', 'full', 'ash @FX@/bare.sh', 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('script:mksh f', 'full', 'full', 'mksh @FX@/bare.sh', 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('script:rbash f', 'full', 'full', 'rbash @FX@/bare.sh', 'allow', '#1656 N2: the create sits in another interpreter or shell'),
    ('script:then . f', 'full', 'full', 'if true; then . @FX@/bare.sh; fi', 'block', ''),
    ('script:do . f', 'full', 'full', 'for i in 1; do . @FX@/bare.sh; done', 'block', ''),
    ('script:brace . f', 'full', 'full', '{ . @FX@/bare.sh; }', 'block', ''),
    ('script:builtin source f', 'full', 'full', 'builtin source @FX@/bare.sh', 'block', ''),
    ('script:command . f', 'full', 'full', 'command . @FX@/bare.sh', 'block', ''),
    ('script:time . f', 'full', 'full', 'time . @FX@/bare.sh', 'block', ''),
    ('script:! . f', 'full', 'full', '! . @FX@/bare.sh', 'block', ''),
    ('script:eval . f', 'full', 'full', "eval '. @FX@/bare.sh'", 'block', ''),
    ('script:eval source f', 'full', 'full', 'eval source @FX@/bare.sh', 'block', ''),
    ("script:sh -c '. f'", 'fast', 'full', "sh -c '. @FX@/bare.sh'", 'block', ''),
    ("script:sh -c 'bash f'", 'full', 'full', "sh -c 'bash @FX@/bare.sh'", 'block', ''),
    ('script:bash f via var path', 'fast', 'full', 'S=@FX@/bare.sh; bash $S', 'allow', 'not claimed (#1645 body)'),
    ('script:bash f via var quoted', 'full', 'full', 'S=@FX@/bare.sh; bash "$S"', 'allow', 'not claimed (#1645 body)'),
    ('script:script that sources another', 'fast', 'full', 'bash @FX@/nested_src.sh', 'block', ''),
    ('script:script that runs bash another', 'full', 'full', 'bash @FX@/nested_bash.sh', 'block', ''),
    ('script:script w/ gh word var', 'full', 'full', 'bash @FX@/indirect.sh', 'block', ''),
    ('script:python3 f.py (calls gh)', 'full', 'full', 'python3 @FX@/py_create.py', 'allow', 'out of scope on purpose (#1656)'),
    ('script:make issue (Makefile)', 'full', 'full', 'make -f @FX@/Makefile issue', 'allow', 'out of scope on purpose (#1656)'),
    ('script:direct exec ./f', 'full', 'full', 'chmod +x @FX@/shebang.sh && @FX@/shebang.sh', 'allow', 'out of scope on purpose (#1656)'),
    ('script:exec direct ./f', 'full', 'full', '@FX@/shebang.sh', 'allow', 'out of scope on purpose (#1656)'),
    ('script:xargs sh f', 'full', 'full', 'echo @FX@/bare.sh | xargs sh', 'allow', 'not claimed (#1645 body)'),
    ('script:find -exec sh f', 'full', 'full', 'find @FX@/bare.sh -exec sh {} \\;', 'block', ''),
    ('script:ls | xargs bash', 'full', 'full', 'echo @FX@/bare.sh | xargs -I{} bash {}', 'block', ''),
    ('script:glob bash f*', 'full', 'full', 'bash @FX@/bar*.sh', 'block', ''),
    ('script:tilde path', 'full', 'full', 'bash ~/does-not-exist.sh', 'block', ''),
    ('script:missing file', 'full', 'full', 'bash /nonexistent/zzz.sh', 'block', ''),
    ('api:api -X POST', 'fast', 'full', '@G@ api -X POST repos/o/r/issues -f title=x', 'block', ''),
    ('api:api --method POST', 'full', 'full', '@G@ api --method POST repos/o/r/issues -f title=x', 'block', ''),
    ('api:api -XPOST', 'full', 'full', '@G@ api -XPOST repos/o/r/issues -f title=x', 'block', ''),
    ('api:api --method=POST', 'full', 'full', '@G@ api --method=POST repos/o/r/issues -f title=x', 'block', ''),
    ('api:api -X post lower', 'full', 'full', '@G@ api -X post repos/o/r/issues -f title=x', 'block', ''),
    ('api:api fields only', 'full', 'full', '@G@ api repos/o/r/issues -f title=x -f body=y', 'block', ''),
    ('api:api -F', 'full', 'full', '@G@ api repos/o/r/issues -F title=x', 'block', ''),
    ('api:api --field', 'full', 'full', '@G@ api repos/o/r/issues --field title=x', 'block', ''),
    ('api:api --raw-field', 'full', 'full', '@G@ api repos/o/r/issues --raw-field title=x', 'block', ''),
    ('api:api --input', 'fast', 'full', '@G@ api repos/o/r/issues --input /tmp/x.json', 'block', ''),
    ('api:api --input -', 'full', 'full', "echo '{}' | @G@ api repos/o/r/issues --input -", 'block', ''),
    ('api:api leading slash', 'full', 'full', '@G@ api -X POST /repos/o/r/issues -f title=x', 'block', ''),
    ('api:api quoted path', 'full', 'full', '@G@ api -X POST "repos/o/r/issues" -f title=x', 'block', ''),
    ('api:api host', 'full', 'full', '@G@ api --hostname github.com -X POST repos/o/r/issues -f title=x', 'block', ''),
    ('api:api -H first', 'full', 'full', "@G@ api -H 'Accept: x' -X POST repos/o/r/issues -f title=x", 'block', ''),
    ('api:api placeholders', 'full', 'full', '@G@ api -X POST repos/{owner}/{repo}/issues -f title=x', 'block', ''),
    ('api:api path in var', 'full', 'full', 'P=repos/o/r/issues; @G@ api -X POST $P -f title=x', 'allow', '#1656 N3: a gh api form the endpoint pattern does not match'),
    ('api:api path in var braces', 'full', 'full', 'P=repos/o/r/@I@s; @G@ api -X POST "${P}" -f title=x', 'allow', '#1656 N3: a gh api form the endpoint pattern does not match'),
    ('api:api path split', 'full', 'full', "@G@ api -X POST repos/o/r/iss''ues -f title=x", 'block', ''),
    ('api:api path via subst', 'full', 'full', '@G@ api -X POST $(echo repos/o/r/issues) -f title=x', 'allow', '#1656 N3: a gh api form the endpoint pattern does not match'),
    ('api:api full url', 'fast', 'full', '@G@ api -X POST https://api.github.com/repos/o/r/issues -f title=x', 'allow', '#1656 N3: a gh api form the endpoint pattern does not match'),
    ('api:api issue import', 'full', 'full', '@G@ api -X POST repos/o/r/import/issues -f title=x', 'allow', '#1656 N3: a gh api form the endpoint pattern does not match'),
    ('api:api graphql createIssue', 'full', 'full', '@G@ api graphql -f query=\'mutation{createIssue(input:{repositoryId:"x",title:"t"}){issue{id}}}\'', 'allow', 'out of scope on purpose (#1656)'),
    ('api:api orgs issue', 'full', 'full', '@G@ api -X POST orgs/o/issues -f title=x', 'allow', ''),
    ('api:api repositories/ID/issues', 'full', 'full', '@G@ api -X POST repositories/123/issues -f title=x', 'allow', '#1656 N3: a gh api form the endpoint pattern does not match'),
    ('api:api env GH_HOST', 'full', 'full', 'GH_HOST=h.test @G@ api -X POST repos/o/r/issues -f title=x', 'block', ''),
    ('api:curl POST issues', 'full', 'full', 'curl -X POST -H \'Authorization: token t\' https://api.github.com/repos/o/r/issues -d \'{"title":"x"}\'', 'allow', 'out of scope on purpose (#1656)'),
    ('api:curl with gh token', 'full', 'full', 'curl -X POST -H "Authorization: Bearer $(@G@ auth token)" https://api.github.com/repos/o/r/issues -d \'{}\'', 'allow', 'out of scope on purpose (#1656)'),
    ('api:api GET list', 'fast', 'full', '@G@ api repos/o/r/issues', 'allow', ''),
    ('api:api GET -X GET', 'full', 'full', '@G@ api -X GET repos/o/r/issues', 'allow', ''),
    ('api:api comment POST', 'full', 'full', '@G@ api -X POST repos/o/r/issues/12/comments -f body=x', 'allow', ''),
    ('api:api one issue GET', 'full', 'full', '@G@ api repos/o/r/issues/12', 'allow', ''),
    ('api:api PATCH issue', 'full', 'full', '@G@ api -X PATCH repos/o/r/issues/12 -f state=closed', 'allow', ''),
    ('misc:alias g=gh', 'fast', 'full', 'alias g=@G@; g @I@ @C@ -t x', 'block', ''),
    ('misc:alias with sub', 'full', 'full', "alias g='@G@ @I@'; g @C@ -t x", 'block', ''),
    ('misc:alias whole', 'full', 'full', "alias mk='@G@ @I@ @C@'; mk -t x", 'block', ''),
    ('misc:function wrapper', 'fast', 'full', 'g() { command @G@ "$@"; }; g @I@ @C@ -t x', 'block', ''),
    ('misc:function keyword', 'full', 'full', 'function g { @G@ "$@"; }; g @I@ @C@ -t x', 'block', ''),
    ('misc:shopt expand alias', 'full', 'full', 'shopt -s expand_aliases; alias g=@G@; g @I@ @C@ -t x', 'block', ''),
    ('misc:export -f', 'fast', 'full', 'g() { @G@ "$@"; }; export -f g; bash -c \'g @I@ @C@ -t x\'', 'allow', 'not claimed (#1645 body)'),
    ('misc:xargs printf', 'full', 'full', "printf '%s\\n' @I@ @C@ -t x | xargs @G@", 'block', ''),
    ('misc:xargs -a file', 'full', 'full', 'xargs -a @FX@/args.txt @G@', 'block', ''),
    ('misc:xargs cat file', 'full', 'full', 'cat @FX@/args.txt | xargs @G@', 'block', ''),
    ('misc:xargs sh -c', 'full', 'full', "echo x | xargs sh -c '@G@ @I@ @C@ -t x'", 'block', ''),
    ('misc:xargs env gh', 'full', 'full', "echo '@I@ @C@ -t x' | xargs env @G@", 'block', ''),
    ('misc:xargs -I verb', 'full', 'full', 'echo @C@ | xargs -I{} @G@ @I@ {} -t x', 'block', ''),
    ('misc:heredoc sh + gh var', 'fast', 'full', "sh <<'EOF'\nG=@G@\n$G @I@ @C@ -t x\nEOF", 'block', ''),
    ('misc:heredoc sh + alias', 'full', 'full', "sh <<'EOF'\nalias g=@G@; g @I@ @C@ -t x\nEOF", 'block', ''),
    ('misc:heredoc escapes sh', 'full', 'full', 'sh <<EOF\n@G@ @I@\\ @C@ -t x\nEOF', 'block', ''),
    ('misc:heredoc backslash char', 'full', 'full', 'bash <<EOF\n@G@ i\\ssue cr\\eate -t x\nEOF', 'block', ''),
    ('misc:heredoc, comment first', 'full', 'full', "bash <<'EOF'\n# note\n@G@ @I@ @C@ -t x\nEOF", 'block', ''),
    ('misc:script indirect (gh var)', 'full', 'full', 'bash @FX@/indirect.sh', 'block', ''),
    ('script:script w/ comment first line', 'full', 'full', 'bash @FX@/comment_first.sh', 'block', ''),
    ('misc:existing clean script', 'full', 'full', 'bash @FX@/clean.sh', 'allow', ''),
    ('misc:script that only mentions create', 'full', 'full', 'bash @FX@/mention.sh', 'block', 'by design: a script the hook cannot read or label-check is refused'),
    ('misc:cd literal && bash existing', 'full', 'full', 'cd @FX@ && bash clean.sh', 'allow', ''),
    ('misc:cd via subst && bash', 'full', 'full', 'cd "$(git rev-parse --show-toplevel)" && bash @FX@/clean.sh', 'allow', ''),
    ('misc:cd var && bash rel', 'full', 'full', 'cd $D && bash clean.sh', 'block', 'by design: a script the hook cannot read or label-check is refused'),
    ('misc:cd .. && bash rel', 'full', 'full', 'cd .. && bash scripts/maintainer_doctor.py', 'block', 'by design: a script the hook cannot read or label-check is refused'),
    ('misc:bash on repo script', 'full', 'full', 'bash plugins/rails-flow/hooks/scripts/guard-bash.sh', 'block', 'by design: a script the hook cannot read or label-check is refused'),
    ('misc:sh -c without create', 'full', 'full', "sh -c 'echo hi'", 'allow', ''),
    ('misc:bash -c with var', 'full', 'full', 'bash -c "$CMD"', 'allow', ''),
    ('misc:bash scripts glob', 'full', 'full', 'for f in scripts/*.sh; do bash $f; done', 'allow', ''),
    ('misc:source .env style', 'full', 'full', 'set -a; . ./.env; set +a', 'block', 'by design: a script the hook cannot read or label-check is refused'),
    ('misc:source venv', 'fast', 'full', 'source .venv/bin/activate', 'block', 'by design: a script the hook cannot read or label-check is refused'),
    ('misc:source ~/.profile', 'full', 'full', 'source ~/.zshrc', 'block', 'by design: a script the hook cannot read or label-check is refused'),
    ('misc:gh pr create (not issue)', 'fast', 'full', '@G@ pr @C@ -t x -b y', 'allow', ''),
    ('misc:gh api GET issues', 'full', 'full', '@G@ api repos/o/r/issues --jq length', 'allow', ''),
    ('misc:gh issue list/view/comment', 'fast', 'full', '@G@ @I@ view 12; @G@ @I@ comment 12 -b x; @G@ @I@ list', 'allow', ''),
    ('comment:comment then create', 'fast', 'full', '# note\n@G@ @I@ @C@ -t x -b y', 'block', ''),
    ('comment:echo # c then create', 'full', 'full', 'echo hi # note\n@G@ @I@ @C@ -t x -b y', 'block', ''),
    ('comment:comment, blank, create', 'full', 'full', '# a\n\n@G@ @I@ @C@ -t x', 'block', ''),
    ('comment:apostrophe in comment then create', 'fast', 'full', "# don't forget\n@G@ @I@ @C@ -t x -b y", 'block', ''),
    ('comment:double quote in comment then create', 'full', 'full', '# say "hi\n@G@ @I@ @C@ -t x -b y', 'block', ''),
    ('comment:backtick in comment', 'full', 'full', '# `x\n@G@ @I@ @C@ -t x', 'block', ''),
    ('comment:comment with trailing backslash then create', 'fast', 'full', '# note \\\n@G@ @I@ @C@ -t x', 'block', ''),
    ('comment:two comments between', 'full', 'full', '# a\n# b\n@G@ @I@ @C@ -t x', 'block', ''),
    ('comment:create, # trailing, create', 'full', 'full', '@G@ @I@ @C@ -t a -l comp:a -l type:b -l prio:c # ok\n@G@ @I@ @C@ -t b', 'block', ''),
    ('comment:; # then newline create', 'full', 'full', 'true; # x\n@G@ @I@ @C@ -t x', 'block', ''),
    ('comment:indented comment then create', 'full', 'full', '   # note\n@G@ @I@ @C@ -t x', 'block', ''),
    ('comment:tab comment then create', 'full', 'full', '\t# note\n@G@ @I@ @C@ -t x', 'block', ''),
    ('comment:{ # c } group', 'full', 'full', '{ # c\n@G@ @I@ @C@ -t x; }', 'block', ''),
    ('comment:( # c )', 'full', 'full', '( # c\n@G@ @I@ @C@ -t x )', 'block', ''),
    ('comment:hash in quoted title, unlabelled', 'full', 'full', '@G@ @I@ @C@ -t "# x" -b y', 'block', ''),
    ('comment:hash word-internal then create', 'full', 'full', 'echo foo#bar; @G@ @I@ @C@ -t x', 'block', ''),
    ('comment:$# then create', 'full', 'full', 'echo $#; @G@ @I@ @C@ -t x', 'block', ''),
    ('comment:${#a[@]} then create', 'full', 'full', 'a=(1); echo ${#a[@]}\n@G@ @I@ @C@ -t x', 'block', ''),
    ('comment:ansi-c hash then create', 'full', 'full', "echo $'#'\n@G@ @I@ @C@ -t x", 'block', ''),
    ('comment:heredoc body hash then create', 'full', 'full', "cat <<'EOF'\n# x\nEOF\n@G@ @I@ @C@ -t x", 'block', ''),
    ('comment:comment in sh -c string', 'full', 'full', "sh -c '# note\n@G@ @I@ @C@ -t x'", 'block', ''),
    ('comment:comment in heredoc to sh', 'full', 'full', "sh <<'EOF'\n# note\n@G@ @I@ @C@ -t x\nEOF", 'block', ''),
    ('comment:script with comment first line', 'full', 'full', 'bash @FX@/comment_first.sh', 'block', ''),
    ('comment:script, apostrophe comment', 'full', 'full', 'bash @FX@/apos_comment.sh', 'block', ''),
    ('comment:script, backslash comment', 'full', 'full', 'bash @FX@/bs_comment.sh', 'block', ''),
    ('comment:two backslash comments', 'full', 'full', '# a \\\n# b \\\n@G@ @I@ @C@ -t x', 'block', ''),
    ('comment:backslash-newline outside a comment joins', 'full', 'full', '@G@ @I@ \\\n@C@ -t x', 'block', ''),
    ('comment:labelled after comment (control)', 'fast', 'full', '# note\n@G@ @I@ @C@ -t x -b y -l comp:a -l type:b -l prio:c', 'allow', ''),
    ('comment:labelled after backslash comment (control)', 'full', 'full', '# note \\\n@G@ @I@ @C@ -t x -b y -l comp:a -l type:b -l prio:c', 'allow', ''),
    ('comment:create only inside a comment (control)', 'full', 'full', '# later: @G@ @I@ @C@\necho hi', 'allow', ''),
    ('comment:hash in quoted body, labelled (control)', 'full', 'full', '@G@ @I@ @C@ -t x -b "see #12" -l comp:a -l type:b -l prio:c', 'allow', ''),
    ('comment:mention after comment (control)', 'full', 'full', "# note\necho '@G@ @I@ @C@'", 'allow', ''),
    ('comment:gh issue list after comment (control)', 'full', 'full', '# note\n@G@ @I@ list', 'allow', ''),
    ('comment:labelled create split by backslash-newline (control)', 'full', 'full', '@G@ @I@ \\\n@C@ -t x -l comp:a -l type:b -l prio:c', 'allow', ''),
    ('file:create at start, file > cap', 'full', 'full', 'bash @FX@/cap_start.sh', 'block', ''),
    ('file:create AFTER the cap', 'fast', 'full', 'bash @FX@/cap_end.sh', 'block', ''),
    ('file:file exactly at the cap', 'full', 'full', 'bash @FX@/cap_exact.sh', 'block', ''),
    ('file:file just under the cap', 'full', 'full', 'bash @FX@/cap_under.sh', 'block', ''),
    ('file:mode 000 file', 'full', 'full', 'bash @FX@/noperm.sh', 'block', ''),
    ('file:a directory', 'full', 'full', 'bash @FX@/adir', 'block', ''),
    ('file:a FIFO (would block)', 'fast', 'full', 'bash @FX@/fifo.sh', 'block', ''),
    ('file:symlink to a script', 'full', 'full', 'bash @FX@/link.sh', 'block', ''),
    ('file:dangling symlink', 'full', 'full', 'bash @FX@/dangling.sh', 'block', ''),
    ('file:CRLF script', 'full', 'full', 'bash @FX@/crlf.sh', 'block', ''),
    ('file:UTF-16 script', 'full', 'full', 'bash @FX@/utf16.sh', 'block', ''),
    ('file:NUL byte before create', 'full', 'full', 'bash @FX@/nul.sh', 'block', ''),
    ('file:UTF-8 BOM script', 'fast', 'full', 'bash @FX@/bom.sh', 'block', ''),
    ('file:invalid UTF-8 script', 'full', 'full', 'bash @FX@/invalid_utf8.sh', 'block', ''),
    ('file:empty script (control)', 'fast', 'full', 'bash @FX@/empty.sh', 'allow', ''),
    ('file:/dev/zero', 'full', 'full', 'bash /dev/zero', 'block', ''),
    ('file:/dev/stdin', 'full', 'full', 'bash /dev/stdin', 'block', ''),
    ('file:/dev/null (control?)', 'fast', 'full', 'bash /dev/null', 'block', '#1656 (moved from #1671): a device file is refused as unreadable'),
    ('file:self-extracting script (NUL payload)', 'fast', 'full', 'bash @FX@/selfextract.sh', 'block', '#1675: any NUL byte refuses a script, so a shell script with a binary payload is refused where an allow is right'),
    ('file:/proc/self/environ', 'full', 'full', 'bash /proc/self/environ', 'block', ''),
    ('file:/dev/fd/0', 'full', 'full', 'bash /dev/fd/0', 'block', '')
)


def _big() -> list[Case]:
    """Commands too large to commit as literals: the hook's 64 KB and 1 MB paths, in each PATH mode."""
    pad = "# " + "x" * 70 + "\n"
    filler = pad * 1900                              # ~137 KB of comment lines
    labelled = " -l comp:a -l type:b -l prio:c"
    shapes = (
        ("create then 137KB filler", CREATE + "\n" + filler, "block"),
        ("137KB filler then create", filler + CREATE, "block"),
        ("create between two 70KB fillers", filler[:70000] + "\n" + CREATE + "\n" + filler[:70000], "block"),
        ("create then 1 long line 300KB", CREATE + "; echo " + "a" * 300000, "block"),
        ("300KB one line then create", "echo " + "a" * 300000 + "; " + CREATE, "block"),
        ("create labelled + 137KB (control)", CREATE + labelled + "\n" + filler, "allow"),
        ("exactly ~65536 bytes then create", ("echo x\n" * 9362)[:65530] + "\n" + CREATE, "block"),
        ("many short lines (20000) then create", "echo\n" * 20000 + CREATE, "block"),
        ("heredoc 137KB body w create inside sh", "sh <<'EOF'\n" + filler + CREATE + "\nEOF", "block"),
        ("quoted echo 137KB w create (mention)", "echo '" + "a" * 137000 + " " + CREATE + "'", "allow"),
    )
    out = []
    for mode in ("full", "nogrep", "notr"):
        for label, cmd, want in shapes:
            if mode != "full" and want == "allow":
                continue        # the no-grep / no-tr paths spend the hook's whole 6 s deadline on 137 KB: that is timing, not logic (#1656)
            tier = "fast" if mode == "full" and label == "create then 137KB filler" else "full"
            out.append(Case(f"size:{label}" + ("" if mode == "full" else f"@{mode}"), tier, mode, cmd, want))
    return out


def cases() -> list[Case]:
    return [Case(*row) for row in _ROWS] + _big()


def fixture_refs(cmd: str) -> set[str]:
    """The fixture names a command reads (`@FX@/name`); `@FX@` alone (a `cd`) names the directory, which always exists."""
    return set(re.findall(r"@FX@/([A-Za-z0-9_.]+)(?![A-Za-z0-9_.*?\[])", cmd))


def materialise(fx, sub) -> None:
    """Write every fixture into FX; SUB resolves the placeholders inside a text fixture."""
    for name, content in FIXTURES.items():
        path = fx / name
        if isinstance(content, str):
            path.write_text(sub(content), encoding="utf-8", newline="")
        else:
            path.write_bytes(content)
    create = sub(CREATE)
    (fx / "adir").mkdir(exist_ok=True)
    (fx / "cap_start.sh").write_bytes((create + "\n").encode() + b"#" * (CAP + 500))
    (fx / "cap_end.sh").write_bytes(b"#" * (CAP + 500) + b"\n" + create.encode())
    (fx / "cap_exact.sh").write_bytes((create + "\n").encode() + b"#" * (CAP - len(create) - 1))
    (fx / "cap_under.sh").write_bytes((create + "\n").encode() + b"#" * (CAP - len(create) - 100))
    (fx / "noperm.sh").write_bytes((create + "\n").encode())
    os.chmod(fx / "noperm.sh", 0o000)
    os.mkfifo(fx / "fifo.sh")
    os.symlink(fx / "bare.sh", fx / "link.sh")
    os.symlink(fx / "nonexistent_target.sh", fx / "dangling.sh")
