# Extending Rails: Templates, Generators, Engines, Rack (Rails 8.1)

For automating your own conventions and hooking into the framework itself.

## Contents
1. Application templates
2. Custom generators
3. Customizing built-in generator output
4. Plugins and engines
5. Rails on Rack (middleware)

---

## 1. Application templates

A template is a Ruby script of generator actions that configures an app —
your team's `rails new` in a file:

```ruby
# template.rb
gem "rspec-rails", group: [:development, :test]
gem_group :test do
  gem "factory_bot_rails"
  gem "capybara"
end

environment 'config.action_mailer.default_url_options = { host: "localhost:3000" }', env: "development"
route 'root to: "pages#home"'

initializer "generators.rb", <<~RUBY
  Rails.application.config.generators do |g|
    g.test_framework :rspec, fixture: false
    g.helper false
    g.stylesheets false
  end
RUBY

after_bundle do
  generate "rspec:install"
  rails_command "db:prepare"
  git add: ".", commit: %(-m "Initial commit from template")
end
```

Apply at creation or to an existing app:

```bash
rails new myapp --skip-test -m template.rb   # or -m https://example.com/template.rb
bin/rails app:template LOCATION=~/template.rb
```

Useful actions: `gem`, `gem_group`, `add_source`, `environment`,
`initializer`, `route`, `rakefile`, `generate`, `rails_command`,
`run` (shell), `git`, `after_bundle`, plus interactive `ask`/`yes?`/`no?`.
All Thor actions (`create_file`, `inject_into_file`, `gsub_file`) work too.

## 2. Custom generators

Generators automate *your* patterns (a service scaffold, an ADR file, a
standard policy object). Generate a generator:

```bash
bin/rails generate generator adr
# create lib/generators/adr/adr_generator.rb
# create lib/generators/adr/USAGE
# create lib/generators/adr/templates/
```

```ruby
# lib/generators/adr/adr_generator.rb
class AdrGenerator < Rails::Generators::NamedBase
  source_root File.expand_path("templates", __dir__)
  argument :status, type: :string, default: "proposed"
  class_option :dir, type: :string, default: "docs/adr"

  def create_adr_file
    template "adr.md.tt", "#{options[:dir]}/#{Time.current.strftime('%Y%m%d')}-#{file_name}.md"
  end
end
```

```erb
<%# lib/generators/adr/templates/adr.md.tt %>
# ADR: <%= human_name %>
Status: <%= status %>
Date: <%= Time.current.to_date %>
```

`NamedBase` gives you `name` plus derived forms (`file_name`, `class_name`,
`human_name`, `table_name`); templates are ERB with the generator as context.
Run with `bin/rails g adr payment-provider accepted --dir=docs/decisions`;
every generator honors `--pretend` (dry run) and has a matching
`bin/rails destroy`.

Compose bigger generators from existing ones with `hook_for :orm,
:test_framework` or explicit `generate "model", "..."` / `invoke` calls.

## 3. Customizing built-in generator output

Two levers, no monkey-patching:

**Config** (`config/application.rb` or an initializer) — turn parts off and
swap frameworks; scaffolds then generate your stack:

```ruby
config.generators do |g|
  g.orm :active_record, primary_key_type: :uuid   # if the app uses UUID PKs
  g.test_framework :rspec, fixture: false
  g.fixture_replacement :factory_bot, dir: "spec/factories"
  g.helper false
  g.jbuilder false
end
```

**Template overrides** — copy any built-in template into
`lib/templates/<generator path>/` and edit; yours wins. Examples:
`lib/templates/erb/scaffold/index.html.erb`,
`lib/templates/rails/scaffold_controller/controller.rb.tt`,
`lib/templates/active_record/model/model.rb.tt`. This is how you make
`bin/rails g scaffold` emit your house style (e.g. `params.expect`, your
partials, Tailwind classes).

## 4. Plugins and engines

- **Plain gem**: extraction with no Rails coupling — just a gem.
- **Plugin** (`rails plugin new yaffle`): a gem that tests against a dummy
  Rails app (`test/dummy`); use for framework extensions (a custom validator,
  an Active Record macro) shared across apps.
- **Mountable engine** (`rails plugin new blorgh --mountable`): a miniature
  Rails app — own models/controllers/views/routes/migrations — namespaced by
  `isolate_namespace Blorgh` so nothing collides with the host:

```ruby
# host app config/routes.rb
mount Blorgh::Engine, at: "/blog"
```

```bash
bin/rails blorgh:install:migrations && bin/rails db:migrate
```

Inside an isolated engine, url helpers are engine-local; reach the host app's
routes via `main_app.root_path` (and the host reaches the engine via
`blorgh.posts_path`). Host apps can override engine views by shadowing the
path (`app/views/blorgh/posts/index.html.erb`) and inject behavior via a
configurable class (`Blorgh.author_class`).

Reality check: engines are how Solid Queue's Mission Control dashboard,
Active Storage, and Action Mailbox work — powerful, but for one app's internal modularity prefer
plain namespaces (`app/models/billing/`) over engines. Extract an engine when
the same feature genuinely ships to multiple apps.

## 5. Rails on Rack (middleware)

A Rails app is a Rack app; requests pass through a middleware stack before
hitting the router. Inspect it:

```bash
bin/rails middleware
```

Manipulate in `config/application.rb`:

```ruby
config.middleware.use MyMiddleware                       # bottom (closest to app)
config.middleware.insert_before Rack::Runtime, MyMiddleware
config.middleware.insert_after ActionDispatch::Static, MyMiddleware
config.middleware.swap ActionDispatch::ShowExceptions, MyExceptionHandler
config.middleware.delete Rack::Runtime
```

A minimal middleware:

```ruby
# lib/middleware/tenant_resolver.rb
class TenantResolver
  def initialize(app) = @app = app

  def call(env)
    request = ActionDispatch::Request.new(env)
    env["myapp.tenant"] = request.subdomain.presence
    @app.call(env)
  end
end
```

(Autoload note: `lib/` isn't eagerly available at config time — `require` the
file in `application.rb` or place middleware under an autoloaded, eager-loaded
path.)

Rack endpoints can also terminate routes directly — useful for tiny,
framework-free endpoints:

```ruby
# config/routes.rb
get "/ping", to: ->(env) { [200, { "Content-Type" => "text/plain" }, ["pong"]] }
mount MyRackApp, at: "/internal"
```

When to write middleware: cross-cutting HTTP concerns (tenant resolution,
request tagging, custom instrumentation) that must run for *every* request
including ones that never reach a controller. Otherwise a `before_action` in
`ApplicationController` is simpler and more Rails-idiomatic.
