# Chinook client demo: evidence and preparation

Reference for the presenter, not spoken. The words are in [RUNBOOK.md](RUNBOOK.md); the glance version is [CUE_SHEET.md](CUE_SHEET.md); the slides are [presentation/client-deck.html](presentation/client-deck.html). Rebuild the HTML presenter pages after editing either Markdown source:

```sh
uv run python scripts/build_presenter_pages.py
```

## The pitch

**Audience:** Chinook's CTO or engineering lead, head of support, and a business sponsor. They tried an agent, it didn't reach production, and they don't know how the open source and LangSmith differ.

**Thesis:** pilots stall on four questions. Two are answered in code with the open source (account isolation, safe actions). Two are answered by LangSmith (why did it do that, did the change help and does it stay good). The demo shows each answer, then proposes a six-week pilot and asks for two owners and a working session.

**Interviewer feedback this version addresses:** speak to Chinook, not to LangChain engineers, and sell the platform, especially LangSmith.

| Feedback | How the script handles it |
| --- | --- |
| Talk to Chinook, not LangChain | Opens on Chinook's stalled pilot; every beat ends with what it means for Chinook's customers, support team, or engineers; implementation defenses moved to Q&A |
| Business and CTO in the room | "Who is in the room" table; business, support, and CTO question banks |
| Sell LangSmith | 12 of 35 minutes; four beats (See, Test, Review, Run) with observed traces/monitoring and a proposed pilot loop; online scoring, routing, and alerts shown only if configured and rehearsed; "why pay" and hosting answers ready |
| Explain the company and stack early | Deck slides 3 and 4 at 2:00, before live software, with customer proof |
| Close like a seller | Pilot phases, success bar set by the client, a specific ask |

## LangSmith features in the demo

| Feature | Beat | Status |
| --- | --- | --- |
| Studio: run the agent, tool calls, approval pause, graph | 7:00 to 16:00, 28:00 | Live; assistants exist on the running dev server |
| Tracing: model and tool steps, latency, tokens, cost | 16:00 | Project `chinook-support` has traces (67 runs, p50 2.4 s, p99 9.5 s, on September 10, 2026) |
| Datasets and experiments with side-by-side comparison | 19:00 | Verified in LangSmith, see below |
| LLM-as-judge plus deterministic evaluators | 19:00 | Verified feedback means on both experiments |
| Annotation queue with human feedback | 23:00 | Verified, see below |
| Prebuilt monitoring dashboard | 25:00 | Automatic per project; confirm it renders |
| Online evaluator, automation rule, alert | 25:00 | **Proposed pilot configuration by default.** Only use the configured path after verifying a scored run reaches the queue; see RUNBOOK |
| Engine | Optional Q&A only | Outside the core demo route |
| Hosting: US/EU cloud, hybrid, self-hosted | Deck 4, Q&A | From langchain.com/pricing; hybrid and self-hosted are Enterprise |

Do not show deployments.

## Recorded experiment evidence

Both experiments use `gpt-5.6`, `reasoning_effort=none`, dataset `chinook-support-345f64fc3f`, the same 22 cases, and two evaluators. Only the prompt differs; tools, middleware, and the security boundary are identical. The candidate prompt adds several instructions, so it's not a test of one sentence.

| Experiment | Must-hold checks | Quality mean | Perfect 5/5 |
| --- | --- | --- | --- |
| [chinook-baseline-e07f3efc](https://smith.langchain.com/o/74f6d6b7-c5c5-4db6-896b-cf34143e0728/datasets/b4c3b1b1-446a-4cac-9f5a-6945e22f8548/compare?selectedSessions=d2adb255-4f88-49db-809c-f7e270a2757b) | 22/22 | 0.905 (4.52/5) | 11/21 |
| [chinook-improved-827c23af](https://smith.langchain.com/o/74f6d6b7-c5c5-4db6-896b-cf34143e0728/datasets/b4c3b1b1-446a-4cac-9f5a-6945e22f8548/compare?selectedSessions=6dd787ba-7676-43b8-b5ce-2296736cfa3d) | 22/22 | 0.971 (4.86/5) | 19/21 |

[Open both](https://smith.langchain.com/o/74f6d6b7-c5c5-4db6-896b-cf34143e0728/datasets/b4c3b1b1-446a-4cac-9f5a-6945e22f8548/compare?selectedSessions=d2adb255-4f88-49db-809c-f7e270a2757b&selectedSessions=6dd787ba-7676-43b8-b5ce-2296736cfa3d). Re-read from the LangSmith API on September 10, 2026: 22 runs each, `scenario_check` mean 1.0 for both, `answer_usefulness` 0.9048 and 0.9714.

The missing-identity case correctly produces no answer, so the judge scores 21. Say "higher judged quality on this sample". Never say "97% accuracy" or "proven in production".

**The currency example (19:00):**

- Baseline `artist` run `01a08376-d4da-76f3-8c98-29d8dcd629c0`: three correct AC/DC tracks and prices, currency unexplained. Judge: 4/5, currency omitted.
- Candidate `artist` run `01a08378-38ec-7ad1-b783-9d16622e158b`: same tracks and prices, plus a line that the catalog has no currency field.
- The baseline judge flagged currency omission in seven answers; the candidate has none of those complaints.

## Human review (23:00)

Queue **Chinook support answer review**, ID `52b64f07-84bd-464c-ae26-4f66bf839e8e`, holds five runs (checked September 10, 2026).

Show `foreign-ticket` run `01a07469-5ec8-77d2-8350-3d5dad6187ba`. It carries human feedback `human_usefulness` = 3 with a reviewer note that begins "Refusal is correct and must not change; the security boundary is working." The judge also scored it 3/5 (premature refusal, missing next step). This run comes from an earlier experiment on the same agent, not from the two experiments above; don't present it as part of that comparison.

The queue's other `foreign-ticket` item, candidate run `01a08377-b319-7430-94f0-4503d1183414`, has only a judge score (3/5) whose critique questions an invoice rule the tool actually enforces. Use it only if asked how a person overrules a wrong judge.

The dataset is generated from `cases()` in `scripts/evaluate.py` and guarded against drift. Don't click "Add to Dataset" in the UI; new reviewed cases go into code and both variants rerun.

## Company facts used on the deck

Checked September 10, 2026. Recheck the week of the meeting.

- [langchain.com/customers](https://www.langchain.com/customers): Klarna "80% decrease in resolution time"; 7K+ teams building on LangSmith; 100M+ traces processed monthly; 5 of 10 Fortune 10. Also lists Toyota North America, Morningstar, Outshift by Cisco, monday.com, C.H. Robinson, MUFG Bank.
- [Klarna case study](https://blog.langchain.com/customers-klarna/): customer support assistant built on LangGraph and LangSmith; 2.5 million conversations; work equivalent to 700 full-time staff.
- [Products overview](https://docs.langchain.com/oss/python/concepts/products): LangChain is the agent framework, LangGraph the runtime it's built on, Deep Agents the batteries-included harness with planning, file systems, and subagents.
- [Pricing](https://www.langchain.com/pricing): Developer (free), Plus, Enterprise; cloud US or EU; hybrid and self-hosted on Enterprise.
- LangSmith [alerts](https://docs.langchain.com/langsmith/alerts), [online evaluations](https://docs.langchain.com/langsmith/online-evaluations), [automation rules](https://docs.langchain.com/langsmith/rules), [dashboards](https://docs.langchain.com/langsmith/dashboards), [Engine](https://docs.langchain.com/langsmith/engine), [masking inputs and outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs).

## Backup story: the grader bug

Older 18-case experiments `chinook-baseline-864a37c2` and `chinook-improved-3cbbd006` scored 16/18. The agent was right; the evaluator mishandled a curly apostrophe in `artist` and an empty result in `no-inventory`. Fixing `check_case` moved both to 18/18 (`chinook-baseline-cdfbef97`, `chinook-improved-4916f64b`). It improved the measurement, not the agent. It appears in the friction beat and as a Q&A backup.

## Demo boundaries

- Customer 1's latest invoice is 382: August 7, 2025, nine items, total 8.91. Customer 2's is 293. No currency field. Historical sample data.
- Studio selects the customer through named assistants. That's the part a real login replaces.
- Tickets are a local stand-in, routed to the customer's assigned rep. No messages, refunds, or external tickets.
- Don't clear tickets for rehearsal; record the rows first.
- No production ROI, cost, or latency claims beyond what LangSmith shows on screen.

## Coverage against the assignment

Preparation only; keep it off the shared screen.

| Requirement | Where |
| --- | --- |
| Prospective customer, mixed business and technical audience | Whole script; "Who is in the room"; three Q&A banks |
| LangChain as a company, OSS, how LangSmith fits, under 10 minutes | 0:00 to 7:00, deck slides 2 to 4 |
| LangChain orchestration, at least two areas of work | Three jobs on one `create_agent` with four tools (7:00 to 16:00) |
| Chinook dataset | Catalog, invoices, customers, `SupportRepId` to `Employee` |
| Runs in LangSmith Studio | All live beats and the graph at 28:00 |
| OSS features that improve the agent (middleware) | 13:00 approval; 28:00 middleware walkthrough; production data policy and failure handling discussed as pilot work |
| Cognitive architecture and why | 28:00 graph, one-agent rationale, when LangGraph or Deep Agents |
| Customers only see their own information | 11:00 live, 28:00 query filter, optional thread-switch proof, offline tests |
| LangSmith features, differentiators, how they tie together | 16:00 to 28:00 as one loop: See, Test, Review, Run |
| Realistic flow of questions | Four prompts plus reject and approve |
| Friction log | 31:00, [FRICTION.md](FRICTION.md) client recap |
| No deployments, minimal slides, no custom UI | Six slides; Studio is the UI |
| 45 minutes: 35 demo plus 10 questions | Run of show |
