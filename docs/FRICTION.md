# Friction and verification log

## Observed during implementation

- **No starter code:** the authoritative worktree contained only the saved plan and review HTML. The implementation was built from that state.
- **Model credential failure:** a minimal request to the configured default model returned HTTP 401 (`AuthenticationError`). The local Agent Server's valid-context run also reached the provider and returned an authentication error. No model-quality claim can be made from these attempts.
- **Project-only credentials:** at the user's request, API keys now come only from this checkout's `.env`, with inherited key fallback disabled. The local file is gitignored and has owner-only permissions. All 17 checks pass; preflight now reports missing local keys rather than trying the inherited key.
- **LangSmith credential absent:** no `LANGSMITH_API_KEY` was available. Cloud traces, experiments, annotation queue access, and the authenticated Studio UI remain unverified.
- **Development identity is not authentication:** the server advertises an integer customer-context field. Missing context is rejected by the runtime schema; the application additionally denies invalid identities and thread-owner changes. Development Studio/API access remains trusted and is not a production authorization layer.
- **Async middleware matters:** the Studio server invokes asynchronously. Customer-boundary checks have both synchronous and asynchronous implementations; blocking SQLite work in async middleware goes through `asyncio.to_thread`.
- **Chinook variations:** this pinned SQL contains dates through 2025 and no currency field. The runbook and evaluation references use the checked-in data, not assumptions from older Chinook tutorials.
- **A security exception is also an OS error:** Python's `PermissionError` subclasses `OSError`. Error handling explicitly leaves authorization failures uncaught before converting data-service OS errors to sanitized tool feedback. The regression check covers this distinction.
- **Evaluation evidence must survive errors:** the first harness saved only at completion and checked cloud dataset size. It now saves after each result, records committed ticket writes even if the final model call fails, and verifies all cloud inputs/reference outputs before evaluating a snapshot. Regression checks cover changed datasets with the same row count and partial-run preservation.

## Verified locally

- 3,503 tracks in the pinned database; all 412 invoice totals agree with their line-item sums.
- Catalog connections reject writes.
- Customer ownership, missing/invalid identity, SQL parameter handling, and unowned-track filtering.
- Atomic thread binding under simultaneous attempts by different customers.
- Actual LangChain/LangGraph interrupt, approve, reject, resume, idempotent replay, and foreign-invoice write denial with scripted model outputs used only in tests.
- Asynchronous graph execution and bounded model loops.
- Local Agent Server starts, responds with `{"ok":true}`, registers the `support` graph, and exposes the expected context schema.
- Evaluation case discovery lists 18 cases without a model call.
- All 16 offline checks pass. A real single-case baseline attempt preserved an `OpenAIAuthenticationError` in `artifacts/baseline-9350626d.json` with `complete: false`; this is access-failure evidence, not a model-quality experiment.
- OpenAI and LangSmith credentials were later corrected locally. `gpt-5.6` preflight passed, and baseline/candidate cloud experiments completed on the same 18-case dataset with 18/18 deterministic checks each. The missing-identity case records a `PermissionError` intentionally; the evaluator counts that expected fail-closed behavior as a pass. No quality lift is claimed from equal scores. The candidate's no-inventory and punctuation-normalization cases required evaluator corrections before the verified rerun.
- Live Agent Server rehearsal succeeded with customer 1 context: invoice 382 was answered with grounded items, and a support request paused at HITL then resumed to a persisted ticket. This validates the runtime path; a fresh Studio thread and a live rejection rehearsal remain presentation preparation.

- **A broken evaluator looks exactly like a broken agent:** the first experiments scored 16/18 and
  named recommendation quality and empty-catalog handling as the weaknesses. Both were false
  negatives from the evaluator: a typographic apostrophe (U+2019) defeating a literal substring
  match, and an empty tool result arriving as the string `"[]"` rather than a parsed list. The
  agent was correct in both. This cost real time and is now the demo's main LangSmith story.
- **Deterministic checks saturate, so they cannot rank two good prompts:** once the evaluator was
  correct, baseline and candidate both passed every case. Four harder cases were added to probe
  exactly what the candidate prompt claims to fix (implicit "unowned" phrasing, genre-vs-query
  argument choice, asking for more tracks than exist, and vague "most recent order" phrasing), and
  the baseline passed all four unaided. On this model the candidate prompt is not the lever;
  reporting that is more useful than manufacturing a win by weakening the baseline.
- **An LLM-as-judge was needed to get a non-saturated quality signal:** `answer_usefulness` scores
  1-5 against the rubric and is deliberately kept separate from `scenario_check`, which measures
  grounding and side effects. The judge returns no score at all for fail-closed cases so an
  authorization refusal can never be scored as a bad customer answer.
- **A stale `langgraph dev` is a live demo hazard:** an older server still holding port 2024 kept
  its previous environment, so runs against the documented Studio URL failed with an
  authentication error while a freshly started server on another port worked. The CLI only warns
  about the port in passing. Kill any old server before rehearsing.
- **Tool arguments matter as much as tool results:** checking only what a tool returned cannot tell
  whether the agent asked the right question. The harness now records tool call arguments too, so
  a case can assert that `exclude_owned=True` was actually set rather than trusting that the
  returned tracks happened not to be owned.

## Observed while rehearsing in Studio

These came out of driving the real Studio UI end to end, not from reading docs. All three are
reproducible against `langgraph dev` 0.13.4 with `langgraph-api` in-memory runtime 0.33.4.

- **Runtime context is not discoverable in the default input panel.** The graph declares
  `context_schema=CustomerContext`, and the server correctly advertises
  `{"customer_id": {"type": "integer"}, "required": ["customer_id"]}` on
  `GET /assistants/{id}/schemas`. Studio's Input panel still shows only `Messages`, so there is no
  obvious place to supply the one field the graph cannot run without. The workaround that actually
  works is to create named assistants that carry the context: `support — customer 1` and
  `support — customer 2`. That turned out to be better than the documented per-run context anyway,
  because context then persists across runs *and* resumes, removing the most likely live-demo
  mistake of forgetting to re-supply identity when approving an interrupt.

- **A human-in-the-loop interrupt offers a raw JSON box instead of the decisions it just declared.**
  The interrupt payload contains `review_configs[0].allowed_decisions: ["approve", "reject"]`, so
  the server knows there are exactly two valid answers. Studio renders a free-text JSON/YAML editor
  and expects the operator to hand-write `{"decisions": [{"type": "approve"}]}`. For a middleware
  whose entire purpose is a safe two-choice gate, hand-authoring the resume payload is more error
  surface than the gate itself.

- **A malformed resume permanently corrupts the thread.** The resume editor is pre-filled with the
  literal `""`. Submitting that reaches `HumanInTheLoopMiddleware` as a string, which then indexes
  it by key and raises `TypeError: string indices must be integers, not 'str'`. The failure is
  written into the checkpoint, so every subsequent resume on that thread replays the same error —
  including a correctly formed `{"decisions": [...]}` payload sent afterwards over the HTTP API.
  The thread is unrecoverable and the run has to be restarted in a new thread. A resume value that
  does not match the interrupt's declared schema should be rejected at the boundary, before it is
  persisted. This cost real rehearsal time and is the single thing most likely to derail a live
  demo, which is why the terminal fallback (`scripts/chat.py`, which prompts for approve/reject
  with no JSON) is worth keeping rehearsed.

- **Interrupts are surfaced with a red `Error` badge.** `GraphInterrupt` is an exception that
  unwinds the graph, so Studio labels a healthy, expected pause the same way it labels a failure.
  Worth narrating during a demo, or the audience reads a working approval gate as a crash.

- **Thread-to-customer binding is enforced, and it surfaces as a raw traceback.** Switching the
  assistant from customer 1 to customer 2 inside an existing thread raises
  `PermissionError("This conversation belongs to another customer. Start a new thread.")` from
  `db.bind_thread`. This is the intended control and it is the strongest isolation evidence in the
  demo: the run dies in `before_agent`, so the model is never invoked, the trace records ~5 ms and
  zero tokens, and there is no prompt to jailbreak. It still reaches the operator as an unformatted
  Python error rather than an explanation, so it needs framing before it is shown.

## Remaining evidence

A live model conversation, live Studio review interactions, observed model failure, measured evaluation comparison, annotation review, and a timed rehearsal require working model and LangSmith access. Scripted-model tests validate control flow and data boundaries; they do not substitute for those live requirements.
