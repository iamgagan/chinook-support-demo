"""The model sees task arguments, never customer identity or SQL."""
from dataclasses import dataclass
from typing import Annotated

from langchain.tools import ToolRuntime, tool
from pydantic import Field

from chinook_support import db


@dataclass
class CustomerContext:
    customer_id: int


def identity(runtime):
    context = runtime.context
    customer_id = context.get("customer_id") if isinstance(context, dict) else getattr(context, "customer_id", None)
    return db.bind_thread(customer_id, runtime.config.get("configurable", {}).get("thread_id"))


@tool
def search_catalog(
    runtime: ToolRuntime[CustomerContext],
    query: Annotated[str, Field(max_length=100)] = "",
    genre: Annotated[str, Field(max_length=100)] = "",
    exclude_owned: bool = False,
    limit: Annotated[int, Field(ge=1, le=10)] = 5,
) -> list[dict]:
    """Search actual tracks by artist, album, or title substring and optional exact genre.

    Empty query matches any artist/title. For genre requests use genre, not query.
    Set exclude_owned=True to remove tracks this customer has already purchased.
    Returns up to 10 tracks with IDs and prices. Empty results mean no matches.
    """
    return db.search_catalog(identity(runtime), query, genre, exclude_owned, limit)


@tool
def list_my_purchases(runtime: ToolRuntime[CustomerContext], limit: Annotated[int, Field(ge=1, le=20)] = 5) -> list[dict]:
    """List the current customer's invoices, newest first. The dataset is historical."""
    return db.list_purchases(identity(runtime), limit)


@tool
def get_my_invoice(runtime: ToolRuntime[CustomerContext], invoice_id: Annotated[int, Field(ge=1)]) -> dict:
    """Read one owned invoice, with line items, unit prices, quantities, and exact totals."""
    return db.invoice_detail(identity(runtime), invoice_id)


@tool
def create_support_request(
    runtime: ToolRuntime[CustomerContext], invoice_id: Annotated[int, Field(ge=1)],
    reason: Annotated[str, Field(min_length=3, max_length=500)],
) -> dict:
    """Create a demo support ticket about an owned invoice, only when explicitly requested.

    Human review is required before execution. This does not issue a refund or contact anyone.
    """
    return db.create_ticket(identity(runtime), runtime.config["configurable"]["thread_id"],
                            runtime.tool_call_id, invoice_id, reason)


TOOLS = [search_catalog, list_my_purchases, get_my_invoice, create_support_request]
