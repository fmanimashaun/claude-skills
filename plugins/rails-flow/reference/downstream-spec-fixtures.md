# Downstream spec fixtures and the git shim

A project's own specs build throwaway git repositories (`git init`, `git add -A`, `git commit`)
under the temp directory. The rails-flow git shim refuses `git add -A` and root `git add .`, so
those specs failed under it (#1999: Retask's 41 git-using specs).

## The contract

Right after `git init` or `git clone`, the spec helper writes an empty file:

```ruby
FileUtils.touch(File.join(repo, ".git", "rails-flow-fixture"))
```

A repository carrying that file, **inside `TMPDIR`**, may be staged with `git add` (`-A`, `.`),
and may have `core.hooksPath` set in its own local config. Nothing else is exempt.

It is a file, not an environment variable, because the environment belongs to the caller.

## Where the shim looks

- **cwd mode** (the spec runs git from the repository, or with `-C <dir>`): `GIT_DIR` and
  `GIT_WORK_TREE` both unset. The shim asks the real git which repository it will use.
- **env mode**: both set. `-C` is refused here. Setting only one is refused.
- A linked worktree is accepted when its common dir carries the file.
- Refused in every mode: `--git-dir`, `--work-tree`, `--namespace`, and `GIT_INDEX_FILE`,
  `GIT_OBJECT_DIRECTORY`, `GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_COMMON_DIR`, `GIT_NAMESPACE`.
- The session project's own marker wins over the fixture file, and a `TMPDIR` that contains the
  project exempts nothing.
- `init.defaultBranch` is an allowed `-c` key, so `git init -b` style specs run.

## What it does not promise

The file is forgeable with `touch`. This is a tripwire against an agent staging the wrong thing
by accident, not a boundary against one that means to (the same limit as the session marker).
