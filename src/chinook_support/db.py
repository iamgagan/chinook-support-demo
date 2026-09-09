"""Small, parameterized data boundary. No model-generated SQL."""
import hashlib
import os
import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=True)
# Credentials come only from this checkout, never an inherited shell key.
_local_env = dotenv_values(ROOT / ".env")
for _key in ("OPENAI_API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"):
    os.environ[_key] = _local_env.get(_key) or ""


def catalog_path():
    return Path(os.getenv("CHINOOK_DB", str(ROOT / "data/chinook.sqlite"))).resolve()


def support_path():
    return Path(os.getenv("SUPPORT_DB", str(ROOT / "data/support.sqlite"))).resolve()


def catalog():
    connection = sqlite3.connect(catalog_path().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def support():
    connection = sqlite3.connect(support_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize():
    path = catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        # Build privately, then publish only a complete database.
        import tempfile
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".sqlite") as tmp:
            with closing(sqlite3.connect(tmp.name)) as connection:
                connection.executescript((ROOT / "data/Chinook_Sqlite.sql").read_text())
                assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            # Hard link fails safely if another setup already created the destination.
            try:
                os.link(tmp.name, path)
            except FileExistsError:
                pass
    support_path().parent.mkdir(parents=True, exist_ok=True)
    if support_path() == path:
        raise ValueError("SUPPORT_DB must differ from CHINOOK_DB")
    with closing(support()) as connection, connection:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS thread_owners (
            thread_id TEXT PRIMARY KEY, customer_id INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tickets (
            request_key TEXT PRIMARY KEY, customer_id INTEGER NOT NULL,
            thread_id TEXT NOT NULL, invoice_id INTEGER NOT NULL,
            reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
            rep_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Additive so an existing demo database keeps its tickets.
        if "rep_id" not in {row[1] for row in connection.execute("PRAGMA table_info(tickets)")}:
            connection.execute("ALTER TABLE tickets ADD COLUMN rep_id INTEGER")


def require_customer(customer_id):
    if type(customer_id) is not int or customer_id < 1:
        raise PermissionError("A valid customer identity is required in runtime context.")
    with closing(catalog()) as connection:
        if not connection.execute("SELECT 1 FROM Customer WHERE CustomerId = ?", (customer_id,)).fetchone():
            raise PermissionError("A valid customer identity is required in runtime context.")
    return customer_id


def support_rep(customer_id):
    """Chinook assigns every customer a sales support agent; escalations follow it."""
    require_customer(customer_id)
    with closing(catalog()) as connection:
        row = connection.execute("""
        SELECT e.EmployeeId AS rep_id, e.FirstName || ' ' || e.LastName AS rep, e.Title AS rep_title
        FROM Customer c JOIN Employee e ON e.EmployeeId = c.SupportRepId
        WHERE c.CustomerId = ?
        """, (customer_id,)).fetchone()
    return dict(row) if row else None


def bind_thread(customer_id, thread_id):
    require_customer(customer_id)
    if not isinstance(thread_id, str) or not thread_id.strip() or len(thread_id) > 200:
        raise PermissionError("A valid thread ID is required.")
    with closing(support()) as connection, connection:
        connection.execute("INSERT OR IGNORE INTO thread_owners VALUES (?, ?)", (thread_id, customer_id))
        owner = connection.execute("SELECT customer_id FROM thread_owners WHERE thread_id = ?", (thread_id,)).fetchone()[0]
        if owner != customer_id:
            raise PermissionError("This conversation belongs to another customer. Start a new thread.")
    return customer_id


def money(value):
    return str(Decimal(str(value)).quantize(Decimal("0.01")))


def list_purchases(customer_id, limit=5):
    require_customer(customer_id)
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    with closing(catalog()) as connection:
        rows = connection.execute("""
        SELECT InvoiceId AS invoice_id, InvoiceDate AS date, Total AS total
        FROM Invoice WHERE CustomerId = ? ORDER BY InvoiceDate DESC, InvoiceId DESC LIMIT ?
        """, (customer_id, limit)).fetchall()
    return [{**dict(row), "total": money(row["total"])} for row in rows]


def invoice_detail(customer_id, invoice_id):
    require_customer(customer_id)
    if type(invoice_id) is not int or invoice_id < 1:
        raise ValueError("invoice_id must be a positive integer")
    with closing(catalog()) as connection:
        invoice = connection.execute("""
        SELECT InvoiceId AS invoice_id, InvoiceDate AS date, Total AS total
        FROM Invoice WHERE CustomerId = ? AND InvoiceId = ?
        """, (customer_id, invoice_id)).fetchone()
        if invoice is None:
            # Same response for nonexistent and foreign invoices; no existence oracle.
            return {"error": "Invoice unavailable for the current customer."}
        lines = connection.execute("""
        SELECT t.TrackId AS track_id, t.Name AS track, ar.Name AS artist,
               il.UnitPrice AS unit_price, il.Quantity AS quantity
        FROM InvoiceLine il JOIN Invoice i ON i.InvoiceId = il.InvoiceId
        JOIN Track t ON t.TrackId = il.TrackId
        JOIN Album al ON al.AlbumId = t.AlbumId JOIN Artist ar ON ar.ArtistId = al.ArtistId
        WHERE i.CustomerId = ? AND i.InvoiceId = ? ORDER BY il.InvoiceLineId
        """, (customer_id, invoice_id)).fetchall()
    items = [{**dict(row), "unit_price": money(row["unit_price"]),
              "line_total": money(Decimal(str(row["unit_price"])) * row["quantity"])} for row in lines]
    return {**dict(invoice), "total": money(invoice["total"]), "items": items,
            "line_total": money(sum((Decimal(i["line_total"]) for i in items), Decimal(0)))}


def search_catalog(customer_id, query="", genre="", exclude_owned=False, limit=5):
    require_customer(customer_id)
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")
    if not isinstance(query, str) or not isinstance(genre, str) or max(len(query), len(genre)) > 100:
        raise ValueError("Search text must be at most 100 characters")
    # Literal substring matching: '%' and '_' in customer text aren't SQL wildcards.
    with closing(catalog()) as connection:
        rows = connection.execute("""
        SELECT t.TrackId AS track_id, t.Name AS track, ar.Name AS artist, al.Title AS album,
               g.Name AS genre, t.UnitPrice AS price
        FROM Track t JOIN Album al ON al.AlbumId = t.AlbumId
        JOIN Artist ar ON ar.ArtistId = al.ArtistId JOIN Genre g ON g.GenreId = t.GenreId
        WHERE (? = '' OR instr(lower(t.Name), lower(?)) > 0
          OR instr(lower(ar.Name), lower(?)) > 0 OR instr(lower(al.Title), lower(?)) > 0)
          AND (? = '' OR lower(g.Name) = lower(?))
          AND (? = 0 OR NOT EXISTS (
            SELECT 1 FROM InvoiceLine il JOIN Invoice i ON i.InvoiceId = il.InvoiceId
            WHERE il.TrackId = t.TrackId AND i.CustomerId = ?))
        ORDER BY t.TrackId LIMIT ?
        """, (query, query, query, query, genre, genre, int(exclude_owned), customer_id, limit)).fetchall()
    return [{**dict(row), "price": money(row["price"])} for row in rows]


def create_ticket(customer_id, thread_id, tool_call_id, invoice_id, reason):
    bind_thread(customer_id, thread_id)
    if not isinstance(tool_call_id, str) or not tool_call_id:
        raise ValueError("A tool call ID is required")
    if not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 500:
        raise ValueError("Provide a reason between 3 and 500 characters")
    if "error" in invoice_detail(customer_id, invoice_id):
        return {"error": "Invoice unavailable for the current customer."}
    key = hashlib.sha256(f"{thread_id}:{tool_call_id}".encode()).hexdigest()
    reason = reason.strip()
    rep = support_rep(customer_id) or {}
    with closing(support()) as connection, connection:
        connection.execute("""INSERT OR IGNORE INTO tickets
            (request_key, customer_id, thread_id, invoice_id, reason, rep_id) VALUES (?, ?, ?, ?, ?, ?)""",
            (key, customer_id, thread_id, invoice_id, reason, rep.get("rep_id")))
        ticket = connection.execute("SELECT * FROM tickets WHERE request_key = ?", (key,)).fetchone()
        if (ticket["customer_id"], ticket["invoice_id"], ticket["reason"]) != (customer_id, invoice_id, reason):
            raise ValueError("An existing request cannot be replayed with different arguments")
    return {"ticket_id": key, "invoice_id": invoice_id, "reason": reason, "status": ticket["status"],
            "assigned_rep": rep.get("rep"), "rep_title": rep.get("rep_title"), "demo_only": True}


if __name__ == "__main__":
    initialize()
    with closing(catalog()) as connection:
        print("Catalog ready:", connection.execute("SELECT COUNT(*) FROM Track").fetchone()[0], "tracks")
    print("Customer 1 latest purchase:", list_purchases(1, 1))
    print("Customer 2 latest purchase:", list_purchases(2, 1))
