# Architecture and runtime

How the Chinook support agent is put together, what happens on a request, and why each decision was
made. The visual companion is [`presentation/runtime-architecture.html`](presentation/runtime-architecture.html),
whose components are pinned to the source lines referenced here.

---

## The rule everything follows

> Anything probabilistic and behavioural can live in the prompt. Cross-cutting execution policy
> belongs in middleware. Domain capabilities belong in tools. Security invariants and data integrity
> belong at deterministic application and database boundaries.

Nothing moves into the prompt merely because the model usually follows it. The test:
**if a control would be violated by a model that ignored its instructions, it is in the wrong layer.**

| Concern | Layer | Where |
| --- | --- | --- |
| Tone, clarification, how to phrase a refusal | prompt | `agent.py` `BASE_PROMPT` / `IMPROVED_PROMPT` |
| Identity revalidation, call limits, error sanitising, approval | middleware | `agent.py` |
| Catalog search, invoice reads, ticket creation | tools | `tools.py` |
| Ownership filters, thread ownership, idempotency, read-only mode | data | `db.py` |

---

## Components

### Agent Server — `langgraph dev`

Hosts the graph on loopback `127.0.0.1:2024`, supplies persistence and thread management, and serves
the API that Studio drives. `langgraph.json` registers one graph:

```json
{"graphs": {"support": "./src/chinook_support/agent.py:graph"}}
```

`graph()` is a factory rather than a module-level object so the server can own the checkpointer.
Nothing else in the process constructs one — `chat.py` and `evaluate.py` each pass their own
`InMemorySaver`, which is why an evaluation run can never collide with a demo thread.

### The agent — one `create_agent`

`build_agent()` assembles a model, four tools, a system prompt, a context schema and five middleware.
It is a LangGraph graph underneath, which is what Studio renders; it was not hand-written because the
generated topology — a model/tool loop with middleware hooks at the right lifecycle points — is
exactly the required shape. An explicit graph would be warranted for control flow this cannot express:
parallel branches, fan-out and gather, or genuine phases.

`variant` selects between the baseline and candidate prompts. Everything else is identical, which is
what makes the two experiments comparable.

The model is pinned with `timeout=45` and `max_retries=1`. For `gpt-5*` it sets
`reasoning_effort="none"` rather than `temperature`, because that family rejects sampling controls and
Chat Completions function calling requires it; determinism is pushed into the prompt and the
evaluators instead.

### Tools — the entire surface the model can touch

Four, in `tools.py`:

| Tool | Reads | Bounds |
| --- | --- | --- |
| `search_catalog` | tracks, albums, artists, genres | query ≤ 100 chars, genre ≤ 100, limit 1–10 |
| `list_my_purchases` | the caller's invoices, newest first | limit 1–20 |
| `get_my_invoice` | one owned invoice with line items | `invoice_id ≥ 1` |
| `create_support_request` | writes a demo ticket | reason 3–500 chars, gated by approval |

No tool accepts a customer ID. Each resolves identity itself through `identity(runtime)`, which reads
the runtime context and re-binds the thread. The model has no parameter through which to express
"who am I", so there is nothing to inject.

### Data boundary — `db.py`

One module owns every query. The catalog opens read-only through a URI:

```python
sqlite3.connect(catalog_path().as_uri() + "?mode=ro", uri=True)
```

so a write against Chinook fails at the driver, not at a code review. The support database is
separate and writable, and `initialize()` refuses to run if the two paths resolve to the same file.

Every customer-scoped query filters on customer and the target row together. `invoice_detail` returns
the *same* response for a nonexistent invoice and for someone else's, so the tool cannot be used as an
existence oracle. Money is normalised through `Decimal(...).quantize()` rather than float arithmetic.

---

## The middleware stack

Order matters; this is the order in `build_agent()`.

**1. `CustomerBoundary`** (custom, `agent.py:51`)

Revalidates identity at three lifecycle points, each with a sync and an async implementation because
the Studio server invokes asynchronously and blocking SQLite work must go through
`asyncio.to_thread`:

- `before_agent` — before anything else in the run
- `wrap_model_call` — before every model call
- `wrap_tool_call` — before every tool execution, **including a resumed one after approval**

That third hook is the important one. An interrupt can be resumed minutes later; without
revalidation, approval would execute against whatever identity happened to be supplied at resume time.

**2. `ModelCallLimitMiddleware`** — 8 per run, 40 per thread, `exit_behavior="end"`

**3. `ToolCallLimitMiddleware`** — 12 per run, 60 per thread, `exit_behavior="end"`

Both bound a runaway loop. At scale they are also a **cost ceiling**: a hard bound of 8 model calls
per run means worst-case spend per conversation can be multiplied out, which an unbounded loop
cannot give you.

**4. `ToolErrorMiddleware(tool_error)`**

Maps exceptions to what the model is allowed to see:

```python
PermissionError            -> None   # re-raised: fails closed, never fed back
sqlite3.Error / OSError    -> "The data service is unavailable..."
ValueError                 -> "Invalid tool arguments..."
anything else              -> None   # fails closed
```

The subtlety worth knowing: **`PermissionError` subclasses `OSError`**, so the authorization branch
must come first or a security failure would be rewritten into a friendly "try again later" and handed
to the model. A regression test covers exactly that ordering.

**5. `HumanInTheLoopMiddleware`**

Interrupts on `create_support_request` only, with `allowed_decisions: ["approve", "reject"]`. Reads
are not gated: they are already bounded by ownership filters and carry no irreversible effect. The
rule is *gate what you cannot undo*.

---

## What happens on a request

1. Studio sends a run to the Agent Server with the message **and** the runtime context
   `{"customer_id": N}`. Identity travels beside the message, never inside it.
2. `CustomerBoundary.before_agent` calls `db.bind_thread(customer_id, thread_id)`:
   `INSERT OR IGNORE` into `thread_owners`, then read back the real owner and compare. A mismatch
   raises `PermissionError` **before the model is invoked** — roughly 5 ms and zero tokens.
3. The agent loops: model call → tool calls → model call, bounded by the two limit middlewares.
4. Tools resolve identity again, call `db.py`, and read SQLite.
5. If the model proposes `create_support_request`, the HITL middleware raises a `GraphInterrupt`
   carrying the tool name, its arguments and the permitted decisions. The graph unwinds and the
   checkpoint is saved.
6. A human resumes with `{"decisions": [{"type": "approve"}]}` or a reject. On approval,
   `wrap_tool_call` revalidates identity, `create_ticket` rechecks invoice ownership, resolves the
   customer's assigned sales rep, and writes one row.
7. Every span streams to LangSmith when `LANGSMITH_TRACING=true`.

**Interrupts are exceptions.** `GraphInterrupt` unwinds the graph, which is why Studio badges a
healthy pause with a red `Error`. Nothing has failed.

---

## Trust boundaries

**Local host** — the Agent Server, the agent, tools, data boundary and both databases run in one
process on loopback. Only three things leave the machine: OpenAI for inference, LangSmith for traces,
and the Studio UI itself.

**Customer isolation** — identity revalidated on every model call and every tool call, ownership
enforced in SQL, thread ownership enforced by a primary key.

**Bounded execution** — call limits and error sanitising around the loop. These govern a region
rather than sitting in the path, which is why the diagram draws them as a boundary and not a node.

**The stated limit:** Studio's operator-selected customer is *simulated* authentication. A production
deployment derives identity from an authenticated session and authorizes thread access before the
graph is invoked. What this design proves is the invariant underneath — one conversation, one
customer — which still holds once real auth is in front of it.

---

## Data model

**Chinook** (read-only) — the pinned upstream schema. Used: `Track`, `Album`, `Artist`, `Genre`,
`Invoice`, `InvoiceLine`, `Customer`, and `Employee` via `Customer.SupportRepId` so an escalation
routes to the sales agent the store already assigned.

**Support** (writable, `data/support.sqlite`) — a clearly labelled demo extension, not part of Chinook:

```sql
thread_owners(thread_id PRIMARY KEY, customer_id NOT NULL)
tickets(request_key PRIMARY KEY, customer_id, thread_id, invoice_id,
        reason, status, rep_id, created_at)
```

`thread_id` as a primary key *is* the isolation invariant. `request_key` is
`sha256(thread_id:tool_call_id)`, so replaying an approval returns the existing ticket rather than
writing a second one, and replaying it with different arguments is rejected outright. Idempotency is
structural, not a matter of the model remembering.

---

## Failure taxonomy

Four classes, diagnosed differently. Only the first is a prompt or model problem.

| Class | Looks like | Found in |
| --- | --- | --- |
| Agent | wrong reasoning, tool or answer | model spans, tool arguments |
| Tool / system | timeouts, SQLite errors, provider 5xx | tool span status |
| Policy | a control correctly refused | the run dies before the model |
| Measurement | the evaluator is wrong, not the agent | trace compared against the reference |

The fourth is the one people skip. The `artist` case in `chinook-baseline-864a37c2` scored zero
because the catalog stores `Let's Get It Up` (`U+0027`) and the model wrote `Let’s Get It Up`
(`U+2019`) — a literal substring match counted two of three. The agent was correct; the evaluator was
not. Fixing `check_case` moved both variants 16/18 → 18/18.

---

## Evaluation runtime

`scripts/evaluate.py` builds a fresh agent with an `InMemorySaver` per case and a separate ticket
database under `artifacts/`, so evaluation never touches demo state.

Two evaluators run on every case:

- **`scenario_check`** — deterministic. Grounding, constraints, prices, invoice totals, authorization
  failure, approval interruption, ticket side effects, and the tool *arguments* the agent chose.
- **`answer_usefulness`** — LLM-as-judge, 1–5 against a rubric, returning no score for fail-closed
  cases so a refusal is never rated as a bad answer.

Deterministic checks are the floor you never drop below; the judge is the gradient you improve along.
Once the deterministic set saturated at 22/22 across variants, only the judge could rank them.

Ordering is load-bearing: a run that already executed — and may already have written a ticket — is
persisted with its deterministic score **before** the judge is attempted, and a judge failure degrades
to an unscored case. A regression test covers it.

The dataset is generated from `cases()` in code, not edited in a UI. `verified_examples()` refuses to
run an experiment if the cloud dataset has drifted from that definition, because a silently changed
dataset invalidates every comparison built on it.

---

## What changes for production

The agent code barely moves; the surface around it does.

- **Identity and access** — authenticated claims instead of an operator dropdown; thread
  authorization before graph invocation; RBAC or policy on tools
- **Data and services** — a service layer rather than direct SQLite; durable checkpointing; a real
  ticketing integration
- **Correctness under retry** — the existing idempotency key carried across service retries and
  redeliveries, not just within a thread
- **Operations** — secrets management, per-tenant rate limits, latency and SLO monitoring, incident
  runbooks
- **Privacy** — PII-aware tracing with redaction before spans leave the process
- **The loop** — evaluation gates in CI so a regression blocks a deploy, and online sampling of
  production traces into the annotation queue

Of those, the evaluation gate is the one worth insisting on. The rest is standard service hardening.

---

## Known limitations

- Studio's operator-selected identity is simulated authentication.
- 22 cases demonstrate the methodology; they do not establish production reliability, and the
  headline improvement is judged by a model on 21 scored cases.
- The judge shares a model family with the agent. Mitigated by deterministic checks and human review,
  but not independent evidence.
- Catalog search is literal substring matching plus exact genre — no semantic search, no ranking, no
  personalisation beyond excluding owned tracks.
- In-memory checkpointing over SQLite: single process, no concurrency story.
- Studio assistants live in the dev server's memory and are recreated by `scripts/setup_studio.py`
  after every restart.
