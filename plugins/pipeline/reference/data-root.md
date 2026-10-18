# The data root: one directory per host for everything a deploy keeps (#2141)

**Our design, the maintainer's decision** (recorded on claude-skills #2141). It was proven first on a production Retask host
(Retask #2094, #2130, #1969, #2154). **Every Kamal fact below is `doctrine-verifier` CONFIRMED against Kamal 2.12.0**, cited by file and
line in the gem source. The docs are silent on most of them, so the source decides, and the boundary is **Kamal 2.12.0**.

## The rule

1. **One data root per host**, `/srv/<service>` (or `DATA_ROOT` in `.kamal/deploy.env`). Every persistent mount is a bind mount under it:
   - the app's `volumes:`, e.g. `"/srv/shop/storage:/rails/storage"`;
   - each accessory's data in **`directories:`**, e.g. `- /srv/shop/postgres:/var/lib/postgresql`.
   - **Never a named Docker volume.** Its data lives wherever Docker keeps volumes, and a move to a new disk misses it.
2. **Accessory data goes in `directories:`, not `volumes:`.** Kamal creates a `directories:` entry, with `mode`/`owner`, before the
   container runs. A `volumes:` entry is passed straight to `--volume` with no `mkdir` (`cli/accessory.rb:24`, `:63-71`;
   `configuration/accessory.rb:101`).
   - An **absolute** host path is used as given.
   - A **relative** one lands at `$PWD/<service>-<accessory>/<name>` (`configuration/accessory.rb:219-233`), where `$PWD` is normally the
     SSH user's home. That is outside the root, so it is refused. An accessory's `service:` key replaces `<service>-<accessory>`
     (`:26-28`).
3. **`bin/check-deploy-volumes` refuses everything else:**
   - a named volume;
   - a bind mount outside the root;
   - a relative accessory directory;
   - a path with `..`;
   - a host path built in ERB.

   It reads `config/deploy.yml` and every `config/deploy.<destination>.yml` overlay. It is the plugin's `scripts/check_deploy_volumes.py`,
   copied into the project.

## Which disk the root is on

`bin/data-root.sh` runs ON THE HOST, as root, from `bin/data-root`, which loops over the hosts with ssh. It decides per host; nothing in
the config names a disk.

| The host has | What happens |
|---|---|
| the root already mounted | nothing changes |
| `/etc/fstab` names the root but it is NOT mounted (a volume that did not come back) | **STOPS**; never falls back to the root disk |
| no extra disk | the root on the root disk, with a **WARNING** line; the deploy carries on |
| one blank extra disk, found | formatted ext4, labelled `DATA_LABEL` (`data-root`), added to `/etc/fstab` **by UUID with `nofail`**, mounted |
| one extra disk carrying our label | mounted as it is, never formatted |
| a found disk with any other filesystem | **refused**: name it in `DATA_DEVICE` and set `DATA_DEVICE_ADOPT=1` to mount it as it is |
| two or more candidate disks | **refused** until `DATA_DEVICE` says which |
| a disk named by `DATA_DEVICE` | the same checks: a whole disk, no partitions, not mounted elsewhere |
| an extra disk while the root already holds data on the root disk | **refused**: mounting would hide it (see "Moving the data root to a new volume") |
| old data not yet moved in (`LEGACY_DATA`), and no `.moved-into-data-root` marker | **STOPS**: a deploy now would boot on an empty root |

Disks of size 0 and loop devices are never candidates. `mkfs` reads `/dev/null`, so over `bash -s` it never consumes the rest of the
script.

## When it runs (Kamal 2.12.0)

- **`pre-connect`**, gated to `deploy`, `redeploy`, `setup`, `app boot` and `accessory boot|reboot|start`. Kamal runs `pre-connect` before
  the first remote command of the process, for every command, **`kamal accessory boot` included** (`cli/base.rb:256-266`;
  `Cli::Accessory#boot` → `prepare` → `on(hosts)`, `cli/accessory.rb:6`, `:332-334`). A command that never connects never runs it.
- **`docker-setup`**, at the end of every `kamal server bootstrap`, and so of `kamal setup`, once every host has Docker
  (`cli/server.rb:62-67`).
- **`bin/data-root`** by hand. `pre-deploy` is not used: it would miss `accessory boot`.

Hooks run on the deploying machine, not the hosts (`cli/base.rb:244-248`). They get these variables:
- `KAMAL_HOSTS` (comma-separated), `KAMAL_COMMAND` and `KAMAL_SUBCOMMAND`;
- `KAMAL_DESTINATION`, only when there is one (`tags.rb:14`, `:27-30`; `cli/base.rb:226-231`).

A hook's non-zero exit aborts the command (`cli/base.rb:250-251`). `-H` skips every hook (`cli/base.rb:29`); a script that has already
run the checks itself may pass it.

## Keep one previous version, prune the rest

- **`retain_containers: 1`** in `config/deploy.yml`. Kamal keeps the newest `retain_containers` stopped containers of the service and
  removes the rest. The default is 5 and the minimum 1 (`configuration.rb:217`, `:378`; `commands/prune.rb:17-27`). It removes every
  service image that no container, running or stopped, uses, so the previous version's image stays (`commands/prune.rb:5-15`, `:30-35`).
- **Of the deploy commands, only `deploy` prunes**, after its boot (`cli/main.rb:46-48`). `redeploy` and `rollback` do not. So
  `.kamal/hooks/post-deploy` runs `bin/kamal prune all` (with `-d` when there is a destination) after them.
  - Kamal runs `post-deploy` after a successful `deploy`, `redeploy` or `rollback`, **outside the deploy lock** (`cli/main.rb:52`, `:82`,
    `:108`), so the hook can take the lock itself.
  - A failed prune warns and exits 0: the release is already live.
- **`kamal rollback <version>`** therefore reaches the release before the current one, and no further.
  - A version with no container is refused with "not available as a container" (`cli/main.rb:96-104`).
  - **That refusal does not raise, and the exit status looks like a normal finish.** Read its output; do not trust its exit code.

## Setting it up in a project

1. Copy the templates from `${CLAUDE_PLUGIN_ROOT}/templates/data-root/`:
   - `bin/data-root` and `bin/data-root.sh` into `bin/`;
   - `kamal-hooks/*` into `.kamal/hooks/`;
   - `${CLAUDE_PLUGIN_ROOT}/scripts/check_deploy_volumes.py` to `bin/check-deploy-volumes`.

   Make them executable.
2. In `config/deploy.yml`:
   - point the app's `volumes:` and each accessory's `directories:` under `/srv/<service>`;
   - add `retain_containers: 1`.

   Then `python3 bin/check-deploy-volumes` must exit 0.
3. In `.kamal/deploy.env`, only when needed: `DATA_ROOT`, `DATA_DEVICE`, `DATA_DEVICE_ADOPT=1`, `LEGACY_DATA` (see below), `DATA_LABEL`,
   `APP_SUBDIRS` (default `storage`: the app's bind mounts, which Kamal does not create, so they are made here, owned by uid 1000).

## Moving existing data in

On a host whose data already lives in named volumes or relative accessory directories:
1. Set `LEGACY_DATA` to those places, e.g. `LEGACY_DATA="volume:shop_storage dir:/root/shop-db/data"`. From then on, every deploy STOPS
   until the move is done.
2. In one stop:
   - stop the app;
   - prepare the root with `bash -s -- --migrating` (`--migrating` is an argument, never an environment variable a deploy could inherit);
   - copy the stored files across and compare the file count AND the total bytes, since a lost empty file changes only the count;
   - move the database, by a dump and restore when the major version changes;
   - write `$DATA_ROOT/.moved-into-data-root` **last, after every check passed**;
   - boot with `-H`.
3. Keep the old copies until the release is verified. They are the rollback.

## Moving the data root to a new volume

When a block volume is attached later:
1. Attach it. Do not format it by hand.
2. Prepare it without mounting over the root: `mkfs.ext4 -L data-root /dev/<new>`, then mount it at `/mnt/root-new`.
3. Copy while the app runs: `rsync -aHAX $DATA_ROOT/ /mnt/root-new/`.
4. **Stop** the app and the accessories.
5. Run `rsync -aHAX --delete` again, then `diff -rq`, which must print nothing.
6. `umount /mnt/root-new`, `mv $DATA_ROOT $DATA_ROOT.root-disk`, `mkdir $DATA_ROOT`, then `DATA_DEVICE=/dev/<new> bin/data-root`. The
   volume carries our label, so it is mounted, never formatted, and goes into fstab by UUID with `nofail`.
7. **Start** the accessories and the app (`--version` pinned), and verify.
8. Keep `$DATA_ROOT.root-disk` until a backup taken from the volume has been checked.
