# From a working chatbot to customer support you can trust

**Status: build complete and measured. Agent, tools, middleware, 20 offline checks, Studio server, runbook, and three verified LangSmith experiments are saved. Deterministic checks pass 22/22 in every variant; the LLM-judge usefulness mean moved 0.905 to 0.971 after acting on judge feedback. Live Studio-server rehearsal covered recommendations, identity refusal, and both approval and rejection. A human annotation-queue review is recorded; a timed rehearsal remains. See [README.md](README.md) and [docs/DEMO.md](docs/DEMO.md).**

Build and demonstrate a Chinook music-store support agent that helps customers discover music and resolve purchase questions—while protecting their information and keeping consequential actions under human control.

**Prove how reliability improves.** Use LangSmith to expose a failure, diagnose its cause, evaluate a targeted fix, and show the measured result.

The demo should leave business stakeholders understanding the value and technical stakeholders understanding how to build, inspect, and improve the system using LangChain’s ecosystem. The outcome is a convincing customer demonstration that shows both how the agent works and how the team can make it more reliable.

## What success looks like

- A working LangChain support bot connected to Chinook, covering at least two areas of work and running in LangSmith Studio.
- Customer isolation enforced in code, plus meaningful middleware controls.
- A connected tracing, evaluation, and improvement workflow in LangSmith.
- Clear explanations of LangChain, LangGraph, Deep Agents, and LangSmith, including why this architecture fits the customer.
- A presentation linking technical behavior to business value, supported by explainable code and an honest friction log.

The assignment allows 2–3 days for the build and 45 minutes for the session: 35 minutes of presentation/demo plus 10 minutes of questions. Introductory business/product explanation must stay under 10 minutes. Use Studio for the experience; do not build a custom UI or demonstrate deployments.

## Approved customer workflows

### 1. Discover music

Example: “Recommend three rock tracks I don’t already own.”

Search the real catalog, consult the current customer’s purchase history, and return actual tracks and prices with a short explanation. Recommendations must respect the requested constraints and avoid invented inventory.

### 2. Explain a purchase

Example: “What was in my most recent order, and why did it cost that much?”

Find the current customer’s invoice and explain its line items and total. Resolve “latest” from the historical dataset rather than assuming recent dates. Requests for another customer’s invoices must not disclose information.

### 3. Escalate a purchase problem

Example: “I have a problem with that purchase. Open a support request.”

Prepare a request linked to an owned invoice, pause for human review, and persist only the approved request. Rejection creates nothing; retrying or resuming must not create duplicates.

Support tickets are a clearly labeled local demo extension to Chinook, not an assignment requirement. No real refunds or external ticketing actions are involved.

## Technical approach

- Use Python, one LangChain `create_agent`, narrow tools, SQLite, and LangSmith Studio. Pin compatible dependency versions during setup and use one available tool-capable model consistently for comparisons.
- Start with four tools: catalog search, own purchase list, own invoice detail, and support-request creation. Do not expose arbitrary SQL execution to the model.
- Let the agent select tools and handle conversational follow-ups. Use its underlying LangGraph runtime for state and interrupt/resume behavior; avoid a separate router or custom graph unless a demonstrated requirement needs one.
- Supply customer identity through trusted runtime context, never from chat or a model-selected customer ID. Fail closed when identity is missing. Bind each conversation thread to the same customer and validate ownership on every customer-data access.
- Use parameterized SQL with explicit ownership filters. Return only fields needed for the workflow. Keep the original Chinook database read-only and store demo tickets separately.
- Treat Studio’s operator-selected identity as simulated authentication. A production service would derive identity from authenticated server context and authorize access to conversation threads; Studio selection alone is not production authentication.
- Add human-in-the-loop middleware for ticket creation, bounded model/tool calls, and clear tool-error handling. Recheck invoice ownership when executing an approved request and enforce a unique request key for duplicate protection.
- Enable LangSmith tracing with identifiable experiment/version metadata. Keep credentials in environment variables and out of source control.

Explain Deep Agents’ planning, filesystem, and delegation capabilities, but do not add them to these short support interactions. Skip a vector database, multi-agent routing, custom frontend, payment integration, and deployment work.

## LangSmith demonstration and evaluation

1. **Studio:** run the customer story and inspect the real agent/tool flow.
2. **Tracing:** investigate an observed failure through model/tool inputs and outputs, latency, and token/cost information where supported.
3. **Dataset:** turn the observed failure into a regression example. Curate approximately 15–20 cases covering recommendations, invoices, privacy, ambiguity, and approvals.
4. **Experiments:** compare baseline and improved behavior on the same cases, model, and settings. Keep security controls in both versions. Use deterministic checks for catalog validity, ownership, totals, and write behavior; use a rubric for answer usefulness.
5. **Human feedback:** review an ambiguous result in an annotation queue and show how feedback informs the next dataset iteration. Verify workspace access to the intended features during setup.

Use a real observed failure rather than manufacturing a success story. Report measured results, including regressions. A small demonstration dataset is evidence of an improvement process, not proof of production reliability.

## Implementation sequence

### Day 1 — Working vertical slice

- Confirm model credentials and LangSmith access; verify local Studio setup early.
- Inspect Chinook and choose reproducible demo customers and invoices.
- Set up pinned dependencies, database initialization, agent, tools, runtime context, tracing, and Studio configuration.
- Demonstrate recommendations and owned invoice lookup in Studio.

**Acceptance:** both core workflows work, and another customer’s invoice is inaccessible.

### Day 2 — Reliability and evidence

- Add approval-gated support requests and execution limits.
- Add runnable checks for isolation, missing identity, approval/rejection, resumption, and duplicate protection.
- Create the evaluation dataset, diagnose a baseline failure, make a targeted improvement, and compare experiments.

**Acceptance:** safe action behavior and a reproducible trace-to-fix-to-evaluation story.

### Day 3 — Rehearse and package

- Write clean-start setup instructions, architecture rationale, demo prompts, and a friction log.
- Rehearse with a reset dataset and verify the complete Studio workflow.
- Retain real saved traces and experiment links as fallback evidence if a live service fails; label saved results clearly.
- Prepare a short proposed-approach message for the assignment’s Slack channel. Review it before sending; no message has been sent.

**Acceptance:** a repeatable, timed demo whose code and tradeoffs the presenter can explain.

## Verification checklist

- [x] Recommendations refer to real tracks, respect constraints, and exclude owned tracks when requested (verified by live 18-case experiments and offline checks).
- [x] Invoice details and totals match Chinook records. (Verified offline with the real graph/tools and scripted model.)
- [x] Missing identity fails closed; chat instructions cannot change customer identity (verified by live 18-case experiments and offline checks).
- [x] Cross-customer invoice requests disclose no private information (verified by live 18-case experiments and offline checks).
- [x] Conversation history does not cross customer boundaries (verified offline and on the live Agent Server; an in-chat identity switch is refused).
- [x] Tickets are not written before approval or after rejection. (Verified offline with the real graph/tools and scripted model.)
- [x] Approval resumes correctly; repeated execution does not duplicate tickets. (Verified offline with the real graph/tools and scripted model.)
- [x] Ticket execution revalidates invoice ownership. (Verified offline with the real graph/tools and scripted model.)
- [x] Tool failures and execution limits produce understandable outcomes. (Verified offline with the real graph/tools and scripted model.)
- [x] Baseline and improved experiments use the same cases and comparable settings (same 22-case dataset `chinook-support-345f64fc3f`, `gpt-5.6`, `reasoning_effort=none`); only the candidate prompt differs.
- [x] The app starts from documented setup and runs in Studio with tracing enabled (local server and cloud traces verified; live conversation, approval and rejection all exercised end to end).
- [x] A real observed failure is diagnosed from a trace and the fix is measured (evaluator false negatives at 16/18, then judge-driven currency fix lifting usefulness 0.905 to 0.971).
- [x] A human review is recorded in the annotation queue: operator scores and notes on `no-inventory`, `artist`, and `foreign-ticket` (the 3/5 case), all from a human source rather than the evaluators.
- [ ] Timed 35-minute rehearsal.
- [x] Proposed-approach message posted to the assignment Slack channel.

## Presentation outline

| Time | Demonstration |
| --- | --- |
| 0–6 min | Customer pain, business value, and ecosystem roles |
| 6–15 min | Live recommendations and purchase support; customer-isolation challenge |
| 15–20 min | Support request approval, rejection, and resumption |
| 20–30 min | Trace, failure diagnosis, dataset, experiment comparison, human feedback |
| 30–33 min | Architecture and code enforcing safety |
| 33–35 min | Friction log, limitations, and proposed customer next step |

Reserve another 10 minutes for questions throughout and at the end.

## Remaining setup inputs

- Actual deadline; the sequence above assumes the assignment’s 2–3 day maximum.
- Available model/provider credentials and LangSmith workspace/project access. Do not paste secret values into the plan.
- Availability of annotation queues and experiment features in the selected workspace; check before relying on them during rehearsal.

## References

- [Original assignment](https://mirror-feeling-d80.notion.site/Deployed-Engineer-Technical-Task-LangChain-and-LangSmith-Demo-2fc808527b178012904dc568d97616d2)
- [Chinook SQLite dataset](https://raw.githubusercontent.com/lerocha/chinook-database/master/ChinookDatabase/DataSources/Chinook_Sqlite.sql)
- [LangChain agents](https://docs.langchain.com/oss/python/langchain/agents)
- [Human-in-the-loop middleware](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- [LangSmith evaluations](https://docs.langchain.com/langsmith/evaluation)
- [Local development and Studio](https://docs.langchain.com/langsmith/local-dev-testing)
