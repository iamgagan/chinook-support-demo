"""Run offline: uv run python -m unittest discover -s tests -v."""
import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from chinook_support import db
from chinook_support.agent import build_agent, tool_error
from chinook_support.tools import TOOLS, CustomerContext


class ScriptedModel(FakeMessagesListChatModel):
    """Only in tests: exercises actual graph/middleware/tools without an API key."""
    def bind_tools(self, tools, **kwargs):
        return self


class FailAfterToolModel(ScriptedModel):
    def _generate(self, messages, **kwargs):
        if any(isinstance(m, ToolMessage) for m in messages):
            raise RuntimeError("secret provider details")
        return super()._generate(messages, **kwargs)


def call(name, args, call_id="test-call"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


class SupportChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {
            "CHINOOK_DB": str(Path(self.temp.name) / "catalog.sqlite"),
            "SUPPORT_DB": str(Path(self.temp.name) / "support.sqlite"),
            "LANGSMITH_TRACING": "false",
        })
        env.start()
        self.addCleanup(env.stop)
        db.initialize()
        self.config = {"configurable": {"thread_id": self.id()}}
        self.context = CustomerContext(customer_id=1)
        self.invoice = db.list_purchases(1, 1)[0]["invoice_id"]

    def graph(self, *responses):
        return build_agent(model=ScriptedModel(responses=list(responses)), checkpointer=InMemorySaver())

    def invoke(self, graph, data=None, context=None):
        return graph.invoke(data or {"messages": [{"role": "user", "content": "Help with my purchase."}]},
                            config=self.config, context=context or self.context)

    def tickets(self):
        with closing(db.support()) as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM tickets")]

    def test_dataset_and_readonly_and_totals(self):
        with closing(db.catalog()) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM Track").fetchone()[0], 3503)
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM Customer")
            invoices = connection.execute("SELECT CustomerId, InvoiceId FROM Invoice").fetchall()
        for customer_id, invoice_id in invoices:
            invoice = db.invoice_detail(customer_id, invoice_id)
            self.assertEqual(Decimal(invoice["total"]), Decimal(invoice["line_total"]))

    def test_isolation_and_parameters(self):
        foreign = db.list_purchases(2, 1)[0]["invoice_id"]
        self.assertEqual(db.invoice_detail(1, foreign), db.invoice_detail(1, 999999))
        self.assertEqual(db.search_catalog(1, query="' OR 1=1 --"), [])
        for identity in [None, True, "1", -1, 999999]:
            with self.assertRaises(PermissionError):
                db.list_purchases(identity)
        for t in TOOLS:
            self.assertNotIn("runtime", t.tool_call_schema.model_fields)
            self.assertNotIn("customer_id", t.tool_call_schema.model_fields)

    def test_credentials_use_project_file_without_global_fallback(self):
        # Fresh child processes avoid changing this test runner's credentials.
        script = '''
import os, sys
from pathlib import Path
from unittest.mock import patch
local = {"OPENAI_API_KEY": "local-test-key"} if sys.argv[1] == "local" else {}
with patch("dotenv.load_dotenv"), patch("dotenv.dotenv_values", return_value=local) as read:
    from chinook_support import db
    assert read.call_args.args[0] == db.ROOT / ".env"
    assert os.environ["OPENAI_API_KEY"] == local.get("OPENAI_API_KEY", "")
    assert os.environ["LANGSMITH_API_KEY"] == ""
    assert os.environ["LANGCHAIN_API_KEY"] == ""
'''
        env = {**os.environ, **dict.fromkeys(
            ["OPENAI_API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"], "inherited-test-key")}
        for mode in ["local", "missing"]:
            subprocess.run([sys.executable, "-c", script, mode], env=env, check=True, capture_output=True)

    def test_unowned_recommendations(self):
        tracks = db.search_catalog(1, genre="Rock", exclude_owned=True, limit=10)
        self.assertEqual(len(tracks), 10)
        with closing(db.catalog()) as connection:
            owned = {r[0] for r in connection.execute("""SELECT il.TrackId FROM InvoiceLine il
                JOIN Invoice i ON il.InvoiceId=i.InvoiceId WHERE i.CustomerId=1""")}
        self.assertTrue(all(t["genre"] == "Rock" and t["track_id"] not in owned for t in tracks))
        self.assertEqual(db.search_catalog(1, genre="Imaginary genre"), [])

    def test_bound_thread_denies_changed_or_missing_identity_before_model(self):
        graph = self.graph(AIMessage(content="Welcome"))
        self.invoke(graph)
        with self.assertRaises(PermissionError):
            self.invoke(graph, context=CustomerContext(2))
        with self.assertRaises(PermissionError):
            graph.invoke({"messages": [{"role": "user", "content": "Hello"}]}, config=self.config)
        self.assertEqual(graph.get_state(self.config).values["messages"][-1].type, "human")

    def test_thread_binding_is_atomic(self):
        def bind(customer):
            try:
                db.bind_thread(customer, "racing-thread")
                return customer
            except PermissionError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(x is not None for x in pool.map(bind, [1, 2])), 1)

    def test_approve_resume_and_idempotency(self):
        args = {"invoice_id": self.invoice, "reason": "Missing download"}
        graph = self.graph(call("create_support_request", args), AIMessage(content="Ticket created"))
        paused = self.invoke(graph)
        self.assertTrue(paused["__interrupt__"])
        self.assertEqual(self.tickets(), [])
        # Even a reviewer resuming the wrong customer's conversation must be blocked.
        with self.assertRaises(PermissionError):
            self.invoke(graph, Command(resume={"decisions": [{"type": "approve"}]}), CustomerContext(2))
        result = self.invoke(graph, Command(resume={"decisions": [{"type": "approve"}]}))
        self.assertFalse(result.get("__interrupt__"))
        self.assertEqual(len(self.tickets()), 1)
        ticket = db.create_ticket(1, self.config["configurable"]["thread_id"], "test-call", **args)
        self.assertEqual(len(self.tickets()), 1)
        self.assertEqual(ticket["ticket_id"], self.tickets()[0]["request_key"])
        with self.assertRaises(ValueError):
            db.create_ticket(1, self.config["configurable"]["thread_id"], "test-call", self.invoice, "Changed reason")

    def test_reject_writes_nothing(self):
        graph = self.graph(call("create_support_request", {"invoice_id": self.invoice, "reason": "Missing download"}),
                           AIMessage(content="No ticket was created"))
        self.invoke(graph)
        self.invoke(graph, Command(resume={"decisions": [{"type": "reject", "message": "Do not create this ticket."}]}))
        self.assertEqual(self.tickets(), [])

    def test_approved_foreign_invoice_still_cannot_write(self):
        foreign = db.list_purchases(2, 1)[0]["invoice_id"]
        graph = self.graph(call("create_support_request", {"invoice_id": foreign, "reason": "Missing download"}),
                           AIMessage(content="Invoice unavailable"))
        self.invoke(graph)
        self.invoke(graph, Command(resume={"decisions": [{"type": "approve"}]}))
        self.assertEqual(self.tickets(), [])

    def test_async_studio_path(self):
        graph = self.graph(call("get_my_invoice", {"invoice_id": self.invoice}), AIMessage(content="Done"))
        result = asyncio.run(graph.ainvoke({"messages": [{"role": "user", "content": "Latest invoice"}]},
                                           config=self.config, context=self.context))
        tools = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        self.assertEqual(json.loads(tools[0].content)["invoice_id"], self.invoice)

    def test_invalid_tool_and_database_errors_are_sanitized(self):
        graph = self.graph(call("list_my_purchases", {"limit": 10000}), AIMessage(content="Try a smaller limit"))
        result = self.invoke(graph)
        self.assertTrue(any(isinstance(m, ToolMessage) and m.status == "error" for m in result["messages"]))
        # Authorization failures must never become a model-visible recoverable message.
        self.assertIsNone(tool_error(PermissionError("secret"), None))
        self.assertNotIn("secret", tool_error(sqlite3.OperationalError("secret"), None))

    def test_async_approval_rejection_and_data_error(self):
        async def scenario():
            graph = self.graph(call("create_support_request", {"invoice_id": self.invoice, "reason": "Download missing"}),
                               AIMessage(content="Created"))
            kwargs = {"config": self.config, "context": self.context}
            paused = await graph.ainvoke({"messages": [{"role": "user", "content": "Create a ticket"}]}, **kwargs)
            self.assertTrue(paused["__interrupt__"])
            self.assertEqual(self.tickets(), [])
            await graph.ainvoke(Command(resume={"decisions": [{"type": "approve"}]}), **kwargs)
            self.assertEqual(len(self.tickets()), 1)
        asyncio.run(scenario())
        graph = self.graph(call("get_my_invoice", {"invoice_id": self.invoice}), AIMessage(content="Please try later"))
        self.config = {"configurable": {"thread_id": "data-error"}}
        with patch("chinook_support.db.invoice_detail", side_effect=sqlite3.OperationalError("secret-path")):
            result = self.invoke(graph)
        messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        self.assertEqual(messages[0].status, "error")
        self.assertIn("unavailable", messages[0].content)
        self.assertNotIn("secret-path", messages[0].content)

    def test_evaluation_checks_do_not_reward_empty_or_wrong_outputs(self):
        from scripts.evaluate import cases, check_case
        examples = cases()
        self.assertEqual(len(examples), 22)
        for example in examples:
            self.assertEqual(check_case(example["inputs"], {}, example["outputs"])["score"], 0)
        example = next(e for e in examples if e["inputs"]["case_id"] == "latest-customer-1")
        correct = {"answer": "Invoice 382 totals 8.91.", "tools": [{"name": "get_my_invoice", "value": db.invoice_detail(1, self.invoice)}]}
        self.assertEqual(check_case(example["inputs"], correct, example["outputs"])["score"], 1)
        correct["answer"] = "Invoice totals 0.99."
        self.assertEqual(check_case(example["inputs"], correct, example["outputs"])["score"], 0)
        example = next(e for e in examples if e["inputs"]["case_id"] == "reject-ticket")
        self.assertEqual(check_case(example["inputs"], {"answer": "Done", "paused": True, "tickets": [{"invoice_id": self.invoice}]}, example["outputs"])["score"], 0)
        example = next(e for e in examples if e["inputs"]["case_id"] == "no-inventory")
        self.assertEqual(check_case(example["inputs"], {"answer": "No match", "tools": [{"name": "search_catalog", "value": {"message": "[]", "status": "success"}}]}, example["outputs"])["score"], 1)
        example = next(e for e in examples if e["inputs"]["case_id"] == "artist")
        self.assertEqual(check_case(example["inputs"], {"answer": "Let’s Get It Up — Track ID 7 — 0.99", "tools": [{"name": "search_catalog", "value": [{"track_id": 7, "track": "Let's Get It Up", "artist": "AC/DC", "price": "0.99", "genre": "Rock"}]}]}, example["outputs"])["score"], 0)
        # An unowned request that never set exclude_owned is a failure even when the
        # named tracks happen not to be owned.
        example = next(e for e in examples if e["inputs"]["case_id"] == "implicit-unowned")
        found = [{"track_id": t, "track": f"T{t}", "artist": "A", "price": "0.99", "genre": "Rock"} for t in (900001, 900002, 900003, 900004)]
        answer = " ".join(f"T{t['track_id']} {t['track_id']} 0.99" for t in found)
        lucky = {"answer": answer, "tools": [{"name": "search_catalog", "value": found}], "calls": [{"name": "search_catalog", "args": {"genre": "Rock"}}]}
        self.assertEqual(check_case(example["inputs"], lucky, example["outputs"])["score"], 0)
        deliberate = {**lucky, "calls": [{"name": "search_catalog", "args": {"genre": "Rock", "exclude_owned": True}}]}
        self.assertEqual(check_case(example["inputs"], deliberate, example["outputs"])["score"], 1)

    def test_ticket_routes_to_the_assigned_support_rep(self):
        """Chinook models a support rep per customer; an escalation must follow it."""
        rep1, rep2 = db.support_rep(1), db.support_rep(2)
        self.assertEqual(rep1["rep"], "Jane Peacock")
        self.assertEqual(rep2["rep"], "Steve Johnson")
        self.assertNotEqual(rep1["rep_id"], rep2["rep_id"])
        ticket = db.create_ticket(1, "rep-thread", "call-1", self.invoice, "Download missing")
        self.assertEqual(ticket["assigned_rep"], rep1["rep"])
        self.assertEqual(ticket["rep_title"], "Sales Support Agent")
        with closing(db.support()) as connection:
            stored = connection.execute(
                "SELECT rep_id FROM tickets WHERE request_key = ?", (ticket["ticket_id"],)).fetchone()
        self.assertEqual(stored["rep_id"], rep1["rep_id"])
        # Replay stays idempotent and keeps the same routing.
        again = db.create_ticket(1, "rep-thread", "call-1", self.invoice, "Download missing")
        self.assertEqual(again["ticket_id"], ticket["ticket_id"])
        self.assertEqual(len(self.tickets()), 1)

    def test_judge_skips_cases_with_no_customer_answer(self):
        """The judge must never invent a usefulness score for a fail-closed run."""
        from scripts.evaluate import cases, judge_answer
        examples = cases()
        example = next(e for e in examples if e["inputs"]["case_id"] == "missing-identity")
        verdict = judge_answer(example["inputs"], {"authorization_error": True, "answer": ""}, example["outputs"])
        self.assertIsNone(verdict["score"])
        example = next(e for e in examples if e["inputs"]["case_id"] == "jazz")
        self.assertIsNone(judge_answer(example["inputs"], {"answer": "   "}, example["outputs"])["score"])

    def test_model_loop_is_bounded(self):
        graph = self.graph(call("list_my_purchases", {"limit": 1}))
        result = self.invoke(graph)
        self.assertLessEqual(sum(isinstance(m, ToolMessage) for m in result["messages"]), 8)
        self.assertIn("limit", result["messages"][-1].content.lower())

    def test_evaluation_records_action_even_when_final_model_call_fails(self):
        from scripts.evaluate import cases, check_case, target
        example = next(e for e in cases() if e['inputs']['case_id'] == 'approve-ticket')
        model = FailAfterToolModel(responses=[call('create_support_request', {
            'invoice_id': self.invoice, 'reason': 'Download missing'})])
        with patch('scripts.evaluate.build_agent', side_effect=lambda **kwargs: build_agent(model=model, **kwargs)):
            outputs = target('improved')(example['inputs'])
        self.assertEqual(outputs['error'], 'RuntimeError')
        self.assertEqual(len(outputs['tickets']), 1)
        self.assertTrue(outputs['tools'])
        self.assertNotIn('secret provider details', json.dumps(outputs))
        self.assertEqual(check_case(example['inputs'], outputs, example['outputs'])['score'], 0)

    def test_local_evaluation_keeps_the_run_when_the_judge_fails(self):
        """A judge outage must not erase an agent run that already executed and may have written."""
        from scripts.evaluate import main
        done = {'answer': 'No matches', 'tools': [], 'tickets': [{'invoice_id': 1, 'status': 'open'}]}
        with patch('scripts.evaluate.db.ROOT', Path(self.temp.name)), \
             patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only-unused'}), \
             patch('sys.argv', ['evaluate.py', '--case', 'no-inventory']), \
             patch('builtins.print'), \
             patch('scripts.evaluate.judge_answer', side_effect=RuntimeError('judge timeout')), \
             patch('scripts.evaluate.target', return_value=Mock(return_value=done)):
            main()
        report = json.loads(next((Path(self.temp.name) / 'artifacts').glob('improved-*.json')).read_text())
        self.assertEqual(len(report['results']), 1)
        self.assertEqual(report['results'][0]['outputs']['tickets'], done['tickets'])
        keys = {s['key']: s for s in report['results'][0]['scores']}
        self.assertIn('scenario_check', keys)
        self.assertIsNone(keys['answer_usefulness']['score'])
        self.assertIn('RuntimeError', keys['answer_usefulness']['comment'])

    def test_cloud_evaluation_rejects_changed_dataset_with_same_size(self):
        from scripts.evaluate import verified_examples
        examples = [{'inputs': {'question': 'Invoice total'}, 'outputs': {'total': '8.91'}}]
        remote = [SimpleNamespace(**examples[0])]
        client = Mock()
        client.has_dataset.return_value = True
        client.list_examples.return_value = remote
        self.assertEqual(verified_examples(client, 'test', examples), remote)
        remote[0].outputs = {'total': '0.99'}
        with self.assertRaises(RuntimeError):
            verified_examples(client, 'test', examples)
        client.create_dataset.assert_not_called()

    def test_local_evaluation_preserves_partial_report_on_error(self):
        from scripts.evaluate import main
        successful = {'answer': 'No matches', 'tools': [], 'tickets': []}
        failed = {**successful, 'error': 'RuntimeError'}
        with patch('scripts.evaluate.db.ROOT', Path(self.temp.name)), \
             patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only-unused'}), \
             patch('sys.argv', ['evaluate.py']), \
             patch('builtins.print'), \
             patch('scripts.evaluate.judge_answer', return_value={'key': 'answer_usefulness', 'score': None, 'comment': 'stubbed'}), \
             patch('scripts.evaluate.target', return_value=Mock(side_effect=[successful, failed])):
            with self.assertRaises(SystemExit):
                main()
        reports = list((Path(self.temp.name) / 'artifacts').glob('improved-*.json'))
        self.assertEqual(len(reports), 1)
        report = json.loads(reports[0].read_text())
        self.assertFalse(report['complete'])
        self.assertEqual(len(report['results']), 2)
        self.assertEqual(report['results'][1]['scores'][0]['score'], 0)


if __name__ == "__main__":
    unittest.main()
