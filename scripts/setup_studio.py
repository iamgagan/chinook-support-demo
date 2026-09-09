"""Create the named Studio assistants the demo depends on.

Studio's input panel does not surface the graph's runtime context, even though the server
advertises it on /assistants/{id}/schemas. Carrying `customer_id` on a named assistant is the
reliable way to supply it, and it survives an interrupt resume, which a per-run context does not.

Run this once against a running `langgraph dev`. It is idempotent.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

from chinook_support import db  # loads the local .env

ASSISTANTS = [("support — customer 1", 1), ("support — customer 2", 2)]


def call(base, path, body=None, method=None):
    request = urllib.request.Request(
        base + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response) if response.status != 204 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:2024",
                        help="Agent Server URL printed by `langgraph dev`")
    parser.add_argument("--graph", default="support")
    args = parser.parse_args()

    try:
        call(args.base_url, "/ok")
    except (urllib.error.URLError, OSError):
        parser.error(f"No Agent Server at {args.base_url}. Start `uv run langgraph dev --no-browser` "
                     "first, and use --base-url if it reported a different port.")

    existing = {a.get("name"): a for a in call(args.base_url, "/assistants/search", {"limit": 100})}
    for name, customer_id in ASSISTANTS:
        db.require_customer(customer_id)
        payload = {"graph_id": args.graph, "name": name, "context": {"customer_id": customer_id}}
        found = existing.get(name)
        if found is None:
            created = call(args.base_url, "/assistants", payload)
            print(f"created  {name}  -> {created['assistant_id']}")
        elif found.get("context") != payload["context"]:
            call(args.base_url, f"/assistants/{found['assistant_id']}",
                 {"context": payload["context"]}, method="PATCH")
            print(f"updated  {name}  -> {found['assistant_id']}")
        else:
            print(f"ok       {name}  -> {found['assistant_id']}")
    print("\nPick one of these in Studio's assistant selector; identity then persists across "
          "runs and resumes, so there is nothing to retype at the approval interrupt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
