# Handoff context

Self-contained brief for continuing this work in another tool. Paste the whole file in.
Everything below was verified by running it, not inferred from the code.

---

## What this is

A take-home for **LangChain's Deployed Engineer** role. The role is customer-facing: you help
companies adopt LangChain's stack. So the exercise is a role-play, not just a build.

**The brief:** demo a customer support bot built with LangChain's open source, plus LangSmith, to a
prospective customer. The customer is a music store. They have tried agent development and failed to
ship anything reliable. They do not understand the difference between the free OSS and the paid
product, or why LangSmith matters. Audience is mixed business and technical.

**Format:** 45 minutes. 35 of demo, 10 of questions. No more than 10 minutes on business framing
before live software. Explicitly: do not build a custom UI, do not demo deployments, a couple of
slides are fine but don't invest in them.

**The literal requirements:**
1. Explain the OSS (LangChain, LangGraph, Deep Agents) and how LangSmith fits
2. Use LangChain to orchestrate a bot covering at least two areas of work
3. Connect to the Chinook dataset
4. Run it in LangSmith Studio
5. Add OSS features to improve the agent (the brief hints at middleware)
6. Demo LangSmith features, including differentiating ones

Original assignment: <https://mirror-feeling-d80.notion.site/Deployed-Engineer-Technical-Task-LangChain-and-LangSmith-Demo-2fc808527b178012904dc568d97616d2>

---

## What was built

A Chinook music-store support agent. One `create_agent` over four scoped tools, running on the local
LangGraph Agent Server with LangSmith Studio as the interface.

**Three workflows:**
1. Music discovery, including excluding tracks the customer already owns
2. Explaining an owned invoice and its line items
3. Opening a demo support ticket, gated behind human approval

**Four tools** (`src/chinook_support/tools.py`): `search_catalog`, `list_my_purchases`,
`get_my_invoice`, `create_support_request`. The model never writes SQL and never sees a customer ID.

**Five middleware** (`src/chinook_support/agent.py`):
- `CustomerBoundary` (custom) — revalidates identity before the model and before tool execution,
  sync and async, including on interrupt resume
- `HumanInTheLoopMiddleware` — interrupts on `create_support_request`
- `ModelCallLimitMiddleware` — 8 per run, 40 per thread
- `ToolCallLimitMiddleware` — 12 per run, 60 per thread
- `ToolErrorMiddleware` — sanitizes data errors, deliberately lets `PermissionError` fail closed

**Security model:** identity comes from trusted runtime context, never chat. Every tool revalidates.
Invoice queries filter on customer and invoice together, and a missing invoice returns the identical
response to someone else's invoice, so there is no existence oracle. Threads are bound to a customer
in SQLite; running a bound thread as a different customer raises `PermissionError` in `before_agent`,
before the model is invoked. Ticket keys are `sha256(thread_id:tool_call_id)`, so replay is
idempotent.

**Stated limit, said out loud in the demo:** Studio is a trusted-operator environment. Selecting a
customer from a dropdown is simulated auth, not production auth.

---

## Verified state

Everything here was confirmed by execution.

| Check | Result |
| --- | --- |
| Offline test suite | 18 tests, all pass, no network |
| Preflight (OpenAI + LangSmith) | both reachable |
| Model | `gpt-5.6`, `reasoning_effort=none` |
| Clean-clone setup from the repo | works: sync, db init, tests all pass |
| Live Studio: recommendations | 3 unowned Rock tracks, IDs + prices + currency caveat |
| Live Studio: invoice | #382, 9 items, total 8.91 |
| Live Studio: chat identity switch | refused |
| Live Studio: thread-binding mismatch | `PermissionError` in `before_agent`, ~5 ms, 0 tokens |
| Live Studio: ticket reject | resumed, zero rows written |
| Live Studio: ticket approve | resumed, ticket ID returned and persisted |

### Experiments

Dataset `chinook-support-345f64fc3f` (id `b4c3b1b1-446a-4cac-9f5a-6945e22f8548`), 22 cases, same
model and settings throughout. Only the candidate prompt differs between runs.

| Experiment | Deterministic | Judge mean | Judged 5/5 |
| --- | --- | --- | --- |
| `chinook-baseline-8ce3044d` | 22/22 | 0.895 | 10/21 |
| `chinook-improved-7cc40033` (v1) | 22/22 | 0.914 | 13/21 |
| `chinook-improved-f9a51018` (v2) | 22/22 | **0.981** | **19/21** |

Two evaluators: `scenario_check` (deterministic grounding, ownership, totals, write behaviour, and
the tool *arguments* chosen) and `answer_usefulness` (LLM-as-judge, 1-5 against a rubric). The judge
returns no score for fail-closed cases, which is why the denominator is 21 rather than 22.

Earlier experiments on the previous 18-case dataset are retained as evidence for the evaluator-bug
story: `chinook-baseline-864a37c2` and `chinook-improved-3cbbd006` at 16/18, then
`chinook-baseline-cdfbef97` and `chinook-improved-4916f64b` at 18/18 after the evaluator was fixed.

Annotation queue `Chinook support answer review` (`52b64f07-84bd-464c-ae26-4f66bf839e8e`) holds human
feedback on three runs, including a `foreign-ticket` case scored 3/5 by both the judge and a person.

### Pinned data facts

- 3,503 tracks; all 412 invoice totals agree with their line-item sums
- Customer 1 latest invoice: **382**, 2025-08-07, total **8.91**, 9 tracks at 0.99
- Customer 2 latest invoice: **293**, 2024-07-13, total **0.99**
- Chinook has **no currency field**. Dates are dataset facts, not recent transactions.

---

## The demo narrative

This is the part that carries the presentation. It is a real sequence that happened, which is why it
survives questioning.

1. **Symptom.** First baseline experiment scored 16/18. Two failures: `artist` and `no-inventory`.
   Looks like a weak agent.
2. **The trace disagrees.** On `artist`, the agent returned three genuine AC/DC tracks with correct
   IDs and prices. The catalog stores `Let's Get It Up` with an ASCII apostrophe; the model wrote
   U+2019. The evaluator matched track names as a literal substring and counted two of three. On
   `no-inventory`, the agent correctly declined to substitute; the empty result reached the evaluator
   as the string `"[]"` rather than a parsed list.
3. **Diagnosis.** Both were false negatives. The agent was right and the evaluation was wrong.
   Without the trace, the rational next step is to "fix" a working agent.
4. **Fix and measure.** The correction went into `check_case`, not the agent: NFKC normalisation with
   quote folding, and accepting both forms of an empty result. Both variants moved 16/18 to 18/18.
5. **The metric then saturates.** All variants hit 22/22, including four cases added specifically to
   probe what the candidate prompt claims to fix. The baseline passed all four unaided. A saturated
   metric cannot rank two good prompts, and weakening the baseline to open a gap would be dishonest.
6. **The judge finds what checks cannot.** `answer_usefulness` flagged the same thing in 10 of 21
   baseline cases: prices quoted as bare numbers. The agent was correctly obeying "never invent a
   currency," but a customer reading `0.99` does not know the unit.
7. **Feedback becomes the next version.** One instruction added to the candidate prompt. Rerun:
   judge mean 0.895 to 0.981, 5/5 cases 10 to 19, currency complaints 10 to 0, deterministic checks
   unchanged at 22/22. Better answers with no control loosened.

---

## Repository

**<https://github.com/iamgagan/chinook-support-demo>** (private). Local branch `cetus` maps to `main`.

```
src/chinook_support/
  agent.py      create_agent, middleware stack, BASE_PROMPT and IMPROVED_PROMPT
  tools.py      four @tool definitions, CustomerContext
  db.py         parameterized data boundary, thread binding, ticket idempotency
scripts/
  evaluate.py   22 cases, both evaluators, local and --cloud modes
  preflight.py  credential check
  chat.py       terminal fallback with no JSON at the interrupt
tests/test_support.py   18 offline checks, scripted models, no network
docs/
  DEMO.md       runbook, live evidence, Q&A, Slack draft
  FRICTION.md   friction and verification log
  HANDOFF.md    this file
  presentation/cue-sheet.html    glanceable reference for during the demo
  presentation/promptbook.html   full spoken script with stage directions
```

### Running it

```sh
uv sync --locked
uv run python -m chinook_support.db
uv run python -m unittest discover -s tests -v     # 18 tests, no API key needed

# live
lsof -ti :2024 | xargs kill 2>/dev/null            # a stale server keeps old keys
uv run python scripts/preflight.py
uv run langgraph dev --no-browser
```

Studio: open the printed URL, pick graph `support`, new thread, runtime context `{"customer_id": 1}`.
Two named assistants exist with context baked in (`support — customer 1`, `support — customer 2`),
which is more reliable than per-run context because identity then survives an interrupt resume.

`.env` needs `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-5.6`, `LANGSMITH_API_KEY`, `LANGSMITH_TRACING=true`,
`LANGSMITH_PROJECT=chinook-support`. It is gitignored and keys are read only from that file.

---

## Known gotchas

These cost real time and will cost it again.

- **Stale server on port 2024.** `langgraph dev` warns about the port in passing and silently moves
  to another one. The old server keeps its previous environment and fails with an authentication
  error. Always kill first.
- **The interrupt resume box is pre-filled with `""`.** Select all and replace it. Submitting the
  placeholder raises `TypeError: string indices must be integers` inside the middleware, and that
  failure is written into the checkpoint — every later resume on that thread replays it, including a
  correct payload sent over the HTTP API. The thread is unrecoverable.
  Valid payloads: `{"decisions": [{"type": "approve"}]}` /
  `{"decisions": [{"type": "reject", "message": "..."}]}`.
- **Interrupts show a red `Error` badge.** `GraphInterrupt` is an exception, so Studio labels an
  expected pause like a failure. Cosmetic.
- **Switching assistants inside an existing thread raises `PermissionError`.** That is the intended
  control, not a bug. Recovery is a new thread.
- **Do not click "Add to Dataset" in the UI.** The dataset is generated from `cases()` in code and
  `verified_examples()` refuses to run an experiment if the cloud dataset has drifted from its
  definition. Adding an example there breaks the next `--cloud` run.
- **Grammarly hooks the JSON resume field** and can insert smart quotes that break the payload.

---

## What is done and what is not

**Done:** build, 18 offline tests, three cloud experiments with a measured improvement, live Studio
walkthrough covering every beat including approve and reject, human annotation review, friction log,
repo pushed, Slack status posted.

**Not done:** a timed 35-minute rehearsal. That is the only remaining item.

**Optional, considered and dropped:** adversarial eval cases beyond the current 22, and a hostile
code review pass.

---

## Honest positions to hold

- The headline improvement is **judge-measured**, on 21 scored cases, by a model in the same family
  as the agent. Deterministic checks are 22/22 across all three variants. Lead with that rather than
  letting someone find it — the correct framing is that safety and grounding never regressed.
- 22 cases demonstrates a process. It does not certify a system.
- Studio's operator-selected identity is simulated authentication.
- Support tickets are a clearly labelled local demo extension to Chinook. No refunds, no external
  system.
- Do not manufacture an improvement by weakening the baseline. The baseline passing everything is a
  reportable result.
