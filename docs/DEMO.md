# Demo runbook

## Opening: first six minutes

“Your prototype can answer questions. The harder question is whether your team can trust its answers and actions. Today we'll follow a music-store customer from discovery to purchase support, then show how we inspect a failure and measure a correction.”

Describe three business outcomes without inventing ROI figures:

- Relevant catalog suggestions help customers discover music they can actually buy.
- Grounded invoice answers handle routine questions without exposing someone else's account.
- Human-reviewed tickets turn an unresolved issue into a controlled next step.

Explain the stack in roughly two minutes: LangChain assembles the agent/tools/middleware; LangGraph supplies stateful execution and pause/resume; Deep Agents is useful when planning/files/delegation justify a larger harness; LangSmith connects development, tracing, evaluation, and human feedback. This demo uses one LangChain agent and Studio.

## Live presentation: 35 minutes plus 10 for questions

| Minute | Action | Evidence and customer value |
| --- | --- | --- |
| 0–6 | Opening and ecosystem | A clear reliability problem and why this stack addresses it |
| 6–10 | Customer 1: recommend three unowned Rock tracks | Actual catalog entries, IDs and prices; inspect the `exclude_owned` tool argument |
| 10–13 | Explain the latest purchase | Invoice 382, total 8.91, with line items grounded in Chinook |
| 13–15 | Ask to become customer 2 and see invoice 293 | Chat does not change identity; unavailable invoice response |
| 15–20 | Request a ticket for invoice 382; inspect, reject, request again, approve | No write before review or after rejection; successful tool result contains a persisted demo ticket ID |
| 20–24 | Open the 16/18 baseline run and read the failed `artist` span | The agent was right and the evaluator was wrong; a red cell is a hypothesis, not a verdict |
| 24–30 | Dataset, three experiments, and the annotation queue | Deterministic 22/22 throughout; judge mean 0.905 to 0.971 after acting on judge feedback; show the queued 3/5 case |
| 30–33 | Show the four tools and boundary/middleware code | Ownership belongs in code; review policy belongs in middleware; replay protection belongs in SQLite |
| 33–35 | Friction and next customer step | What remains uncertain and a measured pilot proposal |

Leave ten minutes for questions throughout and at the end. Do not demonstrate deployment or spend time building slides.

## Rehearsal procedure

1. Run `uv run python scripts/preflight.py`; both services must pass.
2. Run the offline test command in README. Start the local server and open Studio.
3. Create a fresh thread with runtime context `{"customer_id":1}`. Use the prompts from README. Keep context the same for every resume.
4. Verify ticket persistence through the actual tool result. For an operator-only local check, query `data/support.sqlite` using Python's sqlite3; do not expose the database to customers.
5. Start a second thread with `{"customer_id":2}` and confirm its latest invoice is 293. Do not switch identities within the first thread.
6. Run baseline and candidate evaluations with the same model and full case set. Save their experiment links in the evidence section below.
7. Pick an actual failure. Explain whether the cause was retrieval, tool selection, instructions, or evaluation design. If the proposed candidate doesn't fix it, change only the relevant behavior and rerun both comparisons as necessary.
8. Review a failed or ambiguous run in the annotation queue. Apply the rubric; record the correction and how it becomes a regression example.
9. Time the complete sequence. Use saved real traces if live inference fails; explicitly say when showing recorded evidence.

## Live evidence

All runs use `gpt-5.6` with `reasoning_effort=none`, the same 22-case dataset
(`chinook-support-345f64fc3f`, dataset id `b4c3b1b1-446a-4cac-9f5a-6945e22f8548`), and the same two
evaluators. Only the candidate prompt changes between them; the security boundary, tools and
middleware are identical in every run.

| Experiment | Deterministic `scenario_check` | `answer_usefulness` mean | Cases judged 5/5 |
| --- | --- | --- | --- |
| [chinook-baseline-e07f3efc](https://smith.langchain.com/o/74f6d6b7-c5c5-4db6-896b-cf34143e0728/datasets/b4c3b1b1-446a-4cac-9f5a-6945e22f8548/compare?selectedSessions=d2adb255-4f88-49db-809c-f7e270a2757b) | 22/22 | 0.905 (4.52/5) | 11/21 |
| [chinook-improved-827c23af](https://smith.langchain.com/o/74f6d6b7-c5c5-4db6-896b-cf34143e0728/datasets/b4c3b1b1-446a-4cac-9f5a-6945e22f8548/compare?selectedSessions=6dd787ba-7676-43b8-b5ce-2296736cfa3d) | 22/22 | **0.971 (4.86/5)** | **19/21** |

The `missing-identity` case is deliberately unscored by the judge: it has no customer-facing answer
because it fails closed, and a refusal must never be rated as a bad reply.

Earlier runs (`8ce3044d` / `7cc40033` / `f9a51018`) measured the agent before support-rep routing was added; the numbers above describe the shipped code. Experiments on the previous 18-case dataset are retained as the evaluator-bug evidence
described below: `chinook-baseline-864a37c2` and `chinook-improved-3cbbd006` at 16/18, then
`chinook-baseline-cdfbef97` and `chinook-improved-4916f64b` at 18/18 after the evaluator was fixed.

- Annotation queue: `Chinook support answer review`, id `52b64f07-84bd-464c-ae26-4f66bf839e8e`,
  currently holding 6 runs including one the judge scored 3/5 for operator adjudication.
- The local Agent Server was exercised live end to end on the final prompt: grounded unowned Rock
  recommendations with the currency caveat, a refused identity switch, and a support request that
  paused at the interrupt and resumed to a persisted ticket. A separate live thread confirmed the
  rejection path resumes with no ticket written.

Human review is recorded on three runs — `no-inventory`, `artist`, and the 3/5 `foreign-ticket`
case — with operator scores and notes, from a human source rather than the evaluators.

Still pending before the presentation: a timed run-through of the full 35 minutes.

## The observed failure, diagnosed and measured

This is the centrepiece of the LangSmith segment. It is a real failure taken from a real
experiment, not a staged one, and the interesting part is *where* the failure turned out to be.

**1. The symptom.** The first baseline experiment (`chinook-baseline-864a37c2`) scored 16/18.
Two cases failed: `artist` and `no-inventory`. The obvious conclusion is that the agent is
unreliable on recommendations and on empty-catalog handling.

**2. The trace says otherwise.** Open each failed run in LangSmith and read the actual spans:

- `artist`: the agent answered with three genuine AC/DC tracks, correct IDs, correct prices.
  The `search_catalog` span shows the catalog row `Let's Get It Up` with an ASCII apostrophe.
  The model wrote `Let's Get It Up` with a typographic apostrophe (U+2019). Our evaluator matched
  the track name as a literal substring of the answer, so it counted only two grounded tracks
  and reported "Wrong number of grounded recommendations".
- `no-inventory`: the agent correctly said no matches were found and explicitly declined to
  substitute another artist. The `search_catalog` span returned an empty list, but it reached the
  evaluator as a `ToolMessage` whose content was the *string* `"[]"`, not a parsed `[]`. The
  evaluator's equality test missed it.

**3. The diagnosis.** Both failures were false negatives. The agent was right and the evaluation
was wrong. Without the trace, the rational next move would have been to "fix" a working agent by
tightening its prompt, which would have burned a day and made the answers worse.

**4. The fix and the measurement.** The correction went into `check_case`, not the agent:
Unicode NFKC normalisation with quote/dash folding before the substring match, and accepting both
the parsed and serialised forms of an empty tool result. Rerunning the *same* dataset with the
*same* model moved both variants from 16/18 to 18/18
(`chinook-baseline-cdfbef97`, `chinook-improved-4916f64b`).

**5. The lesson for the customer.** A red cell in an experiment is a hypothesis, not a verdict.
An evaluator is code, it has bugs, and a broken evaluator is more dangerous than no evaluator
because it sends the team chasing phantom regressions. LangSmith is what makes the difference
visible, because the trace holds the tool arguments and raw tool results, not just the final text.

**6. Why the deterministic score alone is not enough.** After that fix the deterministic checks
saturate: on the current 22-case dataset every variant scores 22/22, including four cases added
specifically to probe what the candidate prompt claims to fix (`implicit-unowned`, `genre-argument`,
`scarce-artist`, `vague-spend`). The baseline passes all four unaided. A saturated metric cannot
rank two good prompts, and weakening the baseline to manufacture a gap would be dishonest.

**7. The judge finds what the deterministic checks cannot.** Adding `answer_usefulness`, an
LLM-as-judge scoring the rubric 1-5, immediately surfaced a systematic defect no deterministic
check was looking for: in 7 of 21 judged baseline cases the agent quoted prices and totals as bare
numbers. It was obeying its instruction not to invent a currency, but a customer reading "0.99" has
no idea what unit that is. The judge kept returning the same category: *currency omitted*.

**8. Feedback becomes the next iteration, and the gain is measured.** That feedback went into the
candidate prompt as one instruction: state once per reply that the catalog records amounts without
a currency field, never guess a currency, and close with a next step where one applies. Rerunning
the same dataset and model:

- `answer_usefulness` mean 0.905 to 0.971 (4.52/5 to 4.86/5)
- cases judged 5/5: 11/21 to 19/21
- currency complaints: 7 to 0
- deterministic `scenario_check`: 22/22 in every run, so no safety or grounding regression

That is the full loop the customer should take away: trace to diagnose, dataset to hold the
regression, deterministic checks for the things that must never break, a judge for the quality the
checks cannot see, and a measured rerun to prove the change helped rather than assuming it did.

## Likely customer questions

**Why one agent?** These tasks share the same customer context and a four-tool surface. A single tool loop is easy to inspect and evaluate. Separate agents would add coordination without a demonstrated benefit.

**Why not let the model query SQL directly?** The tasks need a small set of queries. Fixed, parameterized queries make ownership enforcement and permitted data exposure easy to inspect. This assignment is not a SQL-agent exercise.

**Is customer isolation just a prompt?** No. Tools derive identity from runtime context; owned invoices are selected with customer and invoice IDs together. The thread binding is checked before model/tool execution. Studio itself is a trusted operator environment; a real customer endpoint needs authentication and thread authorization before graph access.

**Can the model approve its own ticket?** Not through chat or a tool. `HumanInTheLoopMiddleware` interrupts the proposed call. The trusted operator resumes it. No real payment or external support system is involved.

**What if an approved request is retried?** The thread/tool-call identity maps to a unique ticket key. Reexecuting that action returns the existing ticket; conflicting arguments are rejected. A newly requested action has a new tool-call identity.

**Does LangSmith make the agent reliable automatically?** No. It supplies evidence: traces to diagnose behavior, datasets/experiments to test changes, and human feedback to improve coverage. The team still defines quality, fixes failures, and monitors regressions.

**What would you change for production?** Authentication and per-thread authorization, a durable service/checkpointer/database appropriate to concurrent use, operational monitoring, and a larger representative evaluation dataset. These are deployment decisions to discuss, not components to bolt onto this take-home.

**What if the baseline already passes?** Show the actual result. Add realistic harder cases or identify a different measured weakness; do not deliberately break the baseline to stage an improvement.

## Slack draft — not sent

I'm planning a focused Chinook support demo with music discovery, owned-invoice support, and a small human-approved support-ticket extension. I'll use one LangChain `create_agent` with four scoped tools, customer identity supplied outside chat, and middleware for review and bounded execution. Studio will be the interface. The LangSmith story will connect a real trace to a regression example, a targeted change, experiment comparison, and human review. I won't build a custom UI or demo deployment. My assumption is that a clearly labeled local ticket extension is a reasonable way to illustrate controlled actions; please let me know if you'd prefer a different support workflow.
