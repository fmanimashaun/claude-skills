# Deployment with Kamal 2 (Rails 8.1)

## Contents
1. The Kamal model and core commands
2. `config/deploy.yml` — annotated
3. Secrets — `.kamal/secrets` and `credentials:fetch` (8.1)
4. Registry-free deploys (Kamal 2.8, new in 8.1)
5. The generated Dockerfile
6. Accessories (Postgres, etc.)
7. SQLite in production
8. Multiple destinations (staging/production)
9. Production checklist

---

## 1. The Kamal model and core commands

Kamal takes fresh Linux servers (only requirement: SSH access as a user that
can install Docker) and turns them into an app host: it builds your
Dockerfile image, pushes it, runs containers, and fronts them with
**kamal-proxy** for zero-downtime deploys and automatic Let's Encrypt TLS.
Every Rails 8 app ships with it configured.

```bash
kamal setup          # first time: installs Docker, boots accessories, deploys
kamal deploy         # build → push → pull on servers → health-check /up → cut over
kamal redeploy       # deploy without bootstrapping/config push (faster iteration)
kamal rollback [VERSION]  # containers for old versions are kept stopped — instant revert
kamal app logs -f    # tail logs (also: kamal logs)
kamal console        # alias → rails console in the running container
kamal shell          # alias → bash in the running container
kamal dbc            # alias → rails dbconsole
kamal app exec "bin/rails db:migrate"   # one-off command in a new container
kamal details        # what's running where
kamal audit          # who deployed what, when
kamal lock release   # clear a stuck deploy lock after an aborted run
```

Zero-downtime flow: new container boots → kamal-proxy polls `GET /up` (the
generated health-check route; boots the app, raises if it can't) → traffic
cuts over → old container stops (kept for rollback). Deploys drain requests
up to `drain_timeout`.

## 2. `config/deploy.yml` — annotated

What Rails generates, with the parts you actually edit:

```yaml
# Name of your application. Used to uniquely configure containers.
service: myapp

# Name of the container image.
image: your-user/myapp

# Deploy to these servers.
servers:
  web:
    - 192.168.0.1
  # Split job processing onto dedicated hosts when one box isn't enough:
  # job:
  #   hosts:
  #     - 192.168.0.2
  #   cmd: bin/jobs

# Enable SSL auto certification via Let's Encrypt (needs DNS pointed at the
# server and port 443 open). Proxy handles TLS termination.
proxy:
  ssl: true
  host: app.example.com
  # kamal-proxy health-checks GET /up by default before cutover.

# Credentials for your image host (see §3–4; optional since Kamal 2.8).
registry:
  # server: registry.digitalocean.com / ghcr.io / ... (omit for Docker Hub)
  username: your-user
  password:
    - KAMAL_REGISTRY_PASSWORD

# Inject ENV variables into containers (secrets come from .kamal/secrets).
env:
  secret:
    - RAILS_MASTER_KEY
  clear:
    # Run Solid Queue inside the web Puma process. Remove (and add a `job`
    # server role running `bin/jobs`) when you outgrow single-process.
    SOLID_QUEUE_IN_PUMA: true
    # WEB_CONCURRENCY: 2
    # JOB_CONCURRENCY: 3
    # DB_HOST: 192.168.0.2   # when the DB is an accessory on another host

# Aliases for common commands (kamal <alias>).
aliases:
  console: app exec --interactive --reuse "bin/rails console"
  shell: app exec --interactive --reuse "bash"
  logs: app logs -f
  dbc: app exec --interactive --reuse "bin/rails dbconsole"

# Persistent storage — REQUIRED for SQLite and Active Storage local disk.
volumes:
  - "myapp_storage:/rails/storage"

# Bridge fingerprinted assets between versions so old requests during a
# deploy still resolve their CSS/JS.
asset_path: /rails/public/assets

# Configure the image builder.
builder:
  arch: amd64          # build for your servers' architecture
  # remote: ssh://docker@docker-builder-server   # offload building
  # cache: { type: registry }                    # speed up CI builds
```

Deploy-relevant behaviors to know: config changes in `deploy.yml` are pushed
on `kamal deploy` (not `redeploy`); `kamal app exec` runs in a *new*
container (add `--reuse` to run in the live one); migrations run
automatically because the Docker **entrypoint** calls `db:prepare` on boot —
you rarely run `db:migrate` by hand.

## 3. Secrets — `.kamal/secrets` and `credentials:fetch` (8.1)

`.kamal/secrets` is a dotenv-style file (committed; values are *references*,
not secrets) that resolves the names listed under `env.secret` and
`registry.password`:

```bash
# .kamal/secrets

# Option A (default): read from your local environment when deploying
KAMAL_REGISTRY_PASSWORD=$KAMAL_REGISTRY_PASSWORD

# Option B (new in 8.1): pull from encrypted Rails credentials — the low-fi
# secret store; only config/master.key needs to exist on the deploying machine
KAMAL_REGISTRY_PASSWORD=$(bin/rails credentials:fetch kamal.registry_password)

RAILS_MASTER_KEY=$(cat config/master.key)

# Option C: a secrets manager via kamal's adapters
# SECRETS=$(kamal secrets fetch --adapter 1password --account my-account --from Vault/Item KAMAL_REGISTRY_PASSWORD)
# KAMAL_REGISTRY_PASSWORD=$(kamal secrets extract KAMAL_REGISTRY_PASSWORD $SECRETS)
```

Adapters exist for 1Password, Bitwarden, LastPass, AWS Secrets Manager, and
Doppler. Whatever the source: secrets land as ENV in the container;
application-level secrets should still live in **Rails credentials**
(decrypted by `RAILS_MASTER_KEY`) rather than being enumerated one-by-one in
deploy.yml.

## 4. Registry-free deploys (Kamal 2.8, new in 8.1)

Kamal no longer requires Docker Hub/GHCR for basic deploys — by default it
spins up a **local registry** and ships the image to your servers directly.
For a first deploy you can therefore skip registry setup entirely: set
`service`, `image`, a server IP, `proxy.host`, and `RAILS_MASTER_KEY`, then
`kamal setup`. Move to a remote registry (`registry.server:` +
username/password) when you have many servers or want CI-built images.

## 5. The generated Dockerfile

Production-ready out of the box — understand it, rarely edit it:

- **Multi-stage**: a `build` stage installs build tools, runs
  `bundle install` and `assets:precompile` (with a dummy
  `SECRET_KEY_BASE_DUMMY=1` so no real key is needed at build time); the
  final stage copies only the built app + gems. Small image, no compilers.
- **Performance env** baked in: `RUBY_YJIT_ENABLE=1`, jemalloc via
  `LD_PRELOAD`, `RAILS_ENV=production`.
- **Non-root**: runs as user `rails` (1000). If you add packages needing
  root, do it in the build stage.
- **Entrypoint** (`bin/docker-entrypoint`) runs `bin/rails db:prepare` when
  the command is a server start — creates/migrates/seeds databases (all of
  them: primary + queue + cache + cable) automatically on boot.
- **CMD** is `["./bin/thrust", "./bin/rails", "server"]`, `EXPOSE 80` —
  Thruster wraps Puma providing HTTP/2, compression, X-Sendfile, and asset
  caching (see `performance-caching.md`). kamal-proxy talks to port 80.
- Add OS packages (e.g. `libvips` is already there for Active Storage
  variants; add `ffmpeg poppler-utils` for video/PDF previews) in the
  `apt-get install` line of the relevant stage.

## 6. Accessories (Postgres, etc.)

Accessories are long-lived companion containers Kamal manages but does not
redeploy with your app:

```yaml
accessories:
  db:
    image: postgres:17
    host: 192.168.0.2
    port: "127.0.0.1:5432:5432"   # bind to localhost; app reaches it via private net
    env:
      clear:
        POSTGRES_DB: myapp_production
        POSTGRES_USER: myapp
      secret:
        - POSTGRES_PASSWORD
    directories:
      - data:/var/lib/postgresql/data
```

Manage with `kamal accessory boot db`, `... reboot db`, `... logs db`. Point
`config/database.yml` at it via `DB_HOST`/`POSTGRES_PASSWORD` env. Same
pattern serves Redis-needing add-ons if a project requires them — but the
default Solid stack needs none.

## 7. SQLite in production

Fully supported for single-server apps (Rails 8 tuned the adapter: WAL mode,
IMMEDIATE transactions, sensible timeouts — no manual config):

- The **volume mount is non-negotiable**: `myapp_storage:/rails/storage`
  persists `storage/production*.sqlite3` (primary, queue, cache, cable) and
  local Active Storage files across deploys. Without it every deploy wipes
  your data.
- One web server only — SQLite files can't be shared across hosts. Scaling
  beyond one box (or adding dedicated `job:` hosts that need the same DB) is
  the moment to move to Postgres/MySQL as an accessory or managed DB.
- Back up by snapshotting the volume or a cron running `sqlite3 ... .backup`
  / Litestream as an accessory.

## 8. Multiple destinations (staging/production)

`config/deploy.yml` is the shared base; `config/deploy.staging.yml` overlays
it. Deploy with `kamal deploy -d staging`. Secrets can also be split as
`.kamal/secrets.staging` (falls back to `.kamal/secrets-common`). Typical
overlay: different `servers:`, `proxy.host`, and a smaller `env`.

## 9. Production checklist

Before first deploy and after significant changes:

- `RAILS_MASTER_KEY` present in `.kamal/secrets`; `config/master.key` **not**
  committed; credentials contain all app secrets.
- DNS A record → server IP; ports 80/443 open; `proxy.host` matches (Let's
  Encrypt fails otherwise).
- `volumes:` covers `/rails/storage` (SQLite and/or local Active Storage).
- Mailer host set: `config.action_mailer.default_url_options = { host: "app.example.com" }`
  in `production.rb`, and an SMTP/API delivery config.
- `config.force_ssl = true` and `config.assume_ssl = true` (generated
  defaults — keep them; kamal-proxy terminates TLS).
- Background jobs actually running: either `SOLID_QUEUE_IN_PUMA: true` or a
  `job:` server role with `cmd: bin/jobs` — not neither, not both.
- Active Storage service for production chosen (`:local` needs the volume;
  S3/GCS/R2 need credentials + gem). `:azure` no longer exists in 8.1.
- Logs go to STDOUT (default) — view with `kamal logs`; add an APM/error
  subscriber (`Rails.error`) before you need it.
- Run `bin/ci` green, then `kamal setup` (first time) / `kamal deploy`.
- Verify: site loads over https, `kamal app logs` clean, a background job
  processes, `kamal rollback` story understood (previous version listed in
  `kamal app containers`).
