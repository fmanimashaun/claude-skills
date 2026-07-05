# AI & LLM Features in Rails — ruby_llm (Rails 8.1)

The standard for LLM integration in Rails is **ruby_llm** — a Ruby-idiomatic,
nearly dependency-free (Faraday, Zeitwerk, Marcel) library with one unified
API across OpenAI, Anthropic, Gemini, DeepSeek, Bedrock, Ollama, OpenRouter,
and any OpenAI-compatible endpoint, plus first-class Rails persistence.
(langchainrb exists as a Python-LangChain-style abstraction layer; this skill
does not use it — prefer ruby_llm's plain-Ruby approach.) Version series:
1.x; verify current APIs at rubyllm.com if the date is well past mid-2026.

## Contents
1. Install and configure
2. Core chat API
3. Rails persistence — `acts_as_chat`
4. Streaming responses with Hotwire
5. Tools (function calling)
6. Structured output — schemas
7. Embeddings and semantic search (pgvector)
8. Testing AI features
9. Production notes and the companion ecosystem

---

## 1. Install and configure

```ruby
# Gemfile
gem "ruby_llm"
```

```ruby
# config/initializers/ruby_llm.rb
RubyLLM.configure do |config|
  config.anthropic_api_key = Rails.application.credentials.dig(:anthropic, :api_key)
  config.openai_api_key    = Rails.application.credentials.dig(:openai, :api_key)
  # config.gemini_api_key / deepseek_api_key / openrouter_api_key ...
  # config.ollama_api_base = "http://localhost:11434/v1"   # local models

  config.default_model = "claude-sonnet-4-5"   # pick from RubyLLM.models
  config.request_timeout = 120
end
```

Keys live in credentials (`project-setup.md`), never ENV literals in code.
`RubyLLM.models` is a built-in registry (context windows, capabilities,
pricing) — browse `RubyLLM.models.chat_models`, refresh with
`RubyLLM.models.refresh!`.

## 2. Core chat API

```ruby
chat = RubyLLM.chat                                   # default model
chat = RubyLLM.chat(model: "gpt-4o")                  # or per-conversation

chat.with_instructions("You are a facilities-management assistant. Be terse.")
response = chat.ask("Draft a PPM checklist for a 500kVA generator")
response.content        # String
# Multi-turn is automatic — the chat object holds history:
chat.ask("Now compress it to 5 items")

chat.with_temperature(0.2)                 # chainable
chat.ask("Describe this", with: "report.pdf")   # attachments: images/PDFs/audio
```

One API, any provider — switching models is a string change, which is the
whole point: never hand-roll provider HTTP clients.

## 3. Rails persistence — `acts_as_chat`

```bash
bin/rails generate ruby_llm:install
bin/rails db:migrate
# → Chat, Message, ToolCall models + migrations
```

```ruby
class Chat < ApplicationRecord
  acts_as_chat            # has_many :messages; ask/say persist automatically
  belongs_to :user
end

class Message < ApplicationRecord
  acts_as_message         # role, content, token counts
end

class ToolCall < ApplicationRecord
  acts_as_tool_call
end
```

```ruby
chat = user.chats.create!(model_id: "claude-sonnet-4-5")
chat.ask("Summarize open work orders")   # user + assistant messages persisted
chat.messages.order(:created_at)          # full transcript, with token usage
```

You get durable conversations, per-message `input_tokens`/`output_tokens`
for cost reporting, and models that behave like any other Active Record —
scopes, authorization, broadcasts.

## 4. Streaming responses with Hotwire

LLM calls take seconds — never run them in the request cycle. The canonical
shape: controller creates the user message and enqueues a job; the job
streams chunks and broadcasts Turbo Streams (`views-hotwire.md` /
`jobs-and-realtime.md`):

```ruby
# app/controllers/messages_controller.rb
def create
  @chat = Current.user.chats.find(params[:chat_id])
  AiReplyJob.perform_later(@chat.id, params.expect(message: [:content])[:content])
  redirect_to @chat, status: :see_other
end
```

```ruby
# app/jobs/ai_reply_job.rb
class AiReplyJob < ApplicationJob
  queue_as :default

  def perform(chat_id, content)
    chat = Chat.find(chat_id)
    buffer = +""

    chat.ask(content) do |chunk|
      next if chunk.content.blank?
      buffer << chunk.content
      Turbo::StreamsChannel.broadcast_update_to(
        chat, target: "assistant_response",
        html: ApplicationController.helpers.simple_format(buffer)
      )
    end
    # acts_as_chat persisted the final assistant message; a last broadcast
    # (or `broadcasts_to :chat` on Message) swaps the buffer for the record.
  end
end
```

The view subscribes with `turbo_stream_from @chat` and renders an empty
`<div id="assistant_response">` placeholder. Rate-limit the endpoint
(`rate_limit` — `controllers-routing.md`) — every message costs money.

## 5. Tools (function calling)

Let the model call your code — a plain class per capability:

```ruby
# app/tools/work_order_lookup.rb
class WorkOrderLookup < RubyLLM::Tool
  description "Looks up a work order by reference number"
  param :reference, desc: "Work order reference, e.g. WO-2026-104"

  def execute(reference:)
    wo = WorkOrder.find_by(reference:)
    return { error: "Not found" } unless wo
    { status: wo.status, site: wo.site.name, due_on: wo.due_on }
  end
end
```

```ruby
chat.with_tool(WorkOrderLookup)        # or with_tools(A, B, C)
chat.ask("What's the status of WO-2026-104?")
# → model requests the tool → execute runs → result returned → model answers
```

Treat `execute` like a controller action: authorize against the chat's user,
validate inputs, return small serializable hashes, and never let a tool
perform destructive writes without an allowlist/confirmation design — the
model chooses when to call it.

## 6. Structured output — schemas

For extraction/classification where you need a Hash, not prose:

```ruby
# Gemfile: gem "ruby_llm-schema"
class InvoiceExtraction < RubyLLM::Schema
  string :vendor
  number :total
  array :line_items do
    object do
      string :description
      number :amount
    end
  end
end

response = RubyLLM.chat.with_schema(InvoiceExtraction)
                       .ask("Extract the invoice data: #{raw_text}")
response.content   # => Hash matching the schema — validate/cast before persisting
```

Prefer schemas over "reply in JSON" prompting — the provider enforces the
shape. Still treat output as untrusted user input: strong-params-style
slicing before writes.

## 7. Embeddings and semantic search (pgvector)

```ruby
RubyLLM.embed("emergency generator maintenance").vectors   # => [Float, ...]
```

Store and query with PostgreSQL + pgvector via the `neighbor` gem:

```ruby
# migration: enable_extension "vector"; add_column :documents, :embedding, :vector, limit: 1536
class Document < ApplicationRecord
  has_neighbors :embedding
end

# index-time (in a job):
doc.update!(embedding: RubyLLM.embed(doc.content).vectors)

# query-time:
q = RubyLLM.embed(params[:q]).vectors
Document.nearest_neighbors(:embedding, q, distance: "cosine").first(5)
```

That's retrieval; RAG is just: retrieve top-k → interpolate into
`with_instructions`/prompt → `ask`. No framework needed.

## 8. Testing AI features

Apply `testing.md` §9 with extra care:

- **VCR** for integration specs against real providers — and filter every
  key: `c.filter_sensitive_data("<ANTHROPIC_KEY>") { Rails.application.credentials.dig(:anthropic, :api_key) }`
  (repeat per provider). Never commit a cassette before checking it.
- Unit-test around the LLM: instance_double the chat
  (`allow(RubyLLM).to receive(:chat).and_return(fake)`) and assert your
  prompts/tool wiring; assert on **structure** (schema keys, status changes),
  not exact generated prose.
- Tool classes are POROs — spec `execute` directly.
- For output-quality regression testing (evals), see `ruby_llm-tribunal`
  below.

## 9. Production notes and the companion ecosystem

Production rules: all calls in background jobs with retries
(`retry_on Faraday::TimeoutError, wait: :polynomially_longer`); record token
usage (persisted on messages) and alert on cost anomalies; keep prompts in
code/partials under version control, not the database; strip/limit user
input length; log with `Rails.event.notify("ai.reply", chat_id:, model:,
input_tokens:, output_tokens:)` for auditability (`observability.md`).

Companion gems (community — vet before adopting): **ruby_llm-mcp** (consume
Model Context Protocol servers as tools/resources), **ruby_llm-agents**
(agent engine with dashboards, cost analytics, budgets),
**ruby_llm-tribunal** (LLM eval framework — structure checks, hallucination
metrics, automated assertions). Core `ruby_llm` alone covers most product
features; reach for these when you're operating many agents or need formal
evals.
