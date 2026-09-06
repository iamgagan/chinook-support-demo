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

## Remaining evidence

A live model conversation, live Studio review interactions, observed model failure, measured evaluation comparison, annotation review, and a timed rehearsal require working model and LangSmith access. Scripted-model tests validate control flow and data boundaries; they do not substitute for those live requirements.
