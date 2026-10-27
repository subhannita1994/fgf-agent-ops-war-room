from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from typing import Any

import httpx
from databricks.sdk import WorkspaceClient
from openai import OpenAI

from memory import append_message, load_messages
from sql_client import run_query

# Per-team settings come from the app resource config in databricks.yml.
CATALOG = os.environ["CATALOG"]
TEAM = os.environ["TEAM"]
SCHEMA = f"{CATALOG}.{os.environ.get('SCHEMA') or TEAM}"
WAREHOUSE_ID = os.environ["WAREHOUSE_ID"]
# Fully qualified Unity Gateway model service name, e.g. catalog.schema.claude-ai-gateway.
MODEL_ENDPOINT = os.environ["MODEL_ENDPOINT"]

MAX_ATTEMPTS = 25
MAX_TOOL_ROUNDS = 6
LIVE_QUESTION = "Which customers have open sales orders for ACE Bakery below margin right now, during today's promo?"

SYSTEM_PROMPT = (
    "You are the FGF Brands Sales Campaign & Opportunity Agent for the marketing team. "
    "Brands: Stonefire, ACE Bakery, Wonder, D'Italiano, Casa Mendosa, Gadoua, FGF Foodservice. "
    "Retailers: Costco, Walmart, Loblaw, Sobeys, Metro, Save-On-Foods. Regions: ON, QC, BC, AB, Atlantic. "
    "Always answer from tool results, never invent numbers. Be concise and use tables for lists."
)


def _arg(kind: str, description: str) -> dict:
    return {"type": kind, "description": description}


TOOLS = {
    "get_orders_below_margin": (
        "Customer locations with OPEN orders placed today for a brand whose margin is below a threshold, worst first.",
        {"brand": _arg("string", "Brand, e.g. ACE Bakery"), "retailer": _arg("string", "Optional retailer"), "max_margin_pct": _arg("number", "Margin threshold in percent, default 0")},
        ["brand"],
    ),
    "get_order_velocity": (
        "Orders and units for a brand since a given hour today (Toronto time) vs the same window 7 days ago.",
        {"brand": _arg("string", "Brand"), "since_hour": _arg("integer", "Hour of day 0-23, e.g. 9 for 9am")},
        ["brand"],
    ),
    "get_active_promos": (
        "Promotions active today with lift_pct and an underperforming flag (lift below 5%).",
        {"brand": _arg("string", "Optional brand")},
        [],
    ),
    "get_late_orders": (
        "OPEN orders past their requested delivery date, one row per order, most days late first.",
        {"region": _arg("string", "Optional region: ON, QC, BC, AB, Atlantic"), "retailer": _arg("string", "Optional retailer")},
        [],
    ),
    "get_top_customers": (
        "Top n customers by net revenue for a brand in this_quarter or last_quarter.",
        {"brand": _arg("string", "Brand"), "period": {"type": "string", "enum": ["this_quarter", "last_quarter"]}, "n": _arg("integer", "How many, default 10")},
        ["brand", "period"],
    ),
    "compare_retailers": (
        "Side-by-side revenue, units and margin for one brand at two retailers over trailing weeks or month to date.",
        {
            "brand": _arg("string", "Brand"),
            "retailer_a": _arg("string", "First retailer"),
            "retailer_b": _arg("string", "Second retailer (same as retailer_a for a single retailer)"),
            "weeks": _arg("integer", "Trailing weeks, default 4"),
            "month_to_date": _arg("boolean", "true to use the current month instead of trailing weeks"),
        },
        ["brand", "retailer_a", "retailer_b"],
    ),
    "get_declining_skus": (
        "SKU and retailer pairs with week-over-week revenue declines in each of the last N completed weeks.",
        {"weeks": _arg("integer", "Consecutive weeks, default 3")},
        [],
    ),
    "get_budget_vs_actual": (
        "Current month actual vs budget revenue and units by brand and retailer.",
        {"brand": _arg("string", "Optional brand"), "retailer": _arg("string", "Optional retailer")},
        [],
    ),
    "get_customer_contact": (
        "Buyer name, email and phone for one ship-to customer id (e.g. C0001).",
        {"customer_id": _arg("string", "Ship-to customer id")},
        ["customer_id"],
    ),
}
TOOL_SPECS = [
    {"type": "function", "function": {"name": name, "description": desc, "parameters": {"type": "object", "properties": props, "required": req}}}
    for name, (desc, props, req) in TOOLS.items()
]

workspace = WorkspaceClient()


class _DatabricksAuth(httpx.Auth):
    """Attach a fresh OAuth header (app service principal) to every request; the SDK refreshes it."""

    def auth_flow(self, request: httpx.Request):
        request.headers.update(workspace.config.authenticate())
        yield request


# Route through the Unity Gateway model service (MLflow Chat Completions API) instead of /serving-endpoints.
client = OpenAI(
    api_key="unused",  # overridden per request by _DatabricksAuth
    base_url=f"{workspace.config.host.rstrip('/')}/ai-gateway/mlflow/v1",
    http_client=httpx.Client(auth=_DatabricksAuth(), timeout=120),
)


def _sql_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    # Databricks SQL reads 'D''Italiano' as two adjacent literals ('D' 'Italiano' -> 'DItaliano'),
    # so escape with backslashes instead: backslash first, then the single quote.
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _timed_query(statement: str, stats: dict[str, float]) -> list[dict]:
    started = time.perf_counter()
    try:
        return run_query(statement)
    finally:
        stats["sql_ms"] = stats.get("sql_ms", 0.0) + (time.perf_counter() - started) * 1000


def call_tool(name: str, arguments: dict[str, Any], stats: dict[str, float] | None = None) -> list[dict]:
    if name not in TOOLS:
        raise ValueError(f"Unknown tool {name}")
    allowed = TOOLS[name][1]
    named_args = ", ".join(f"{k} => {_sql_literal(v)}" for k, v in arguments.items() if k in allowed and v is not None)
    return _timed_query(f"SELECT * FROM {SCHEMA}.{name}({named_args})", stats if stats is not None else {})


@lru_cache(maxsize=1)
def warehouse_name() -> str:
    try:
        return workspace.warehouses.get(WAREHOUSE_ID).name or WAREHOUSE_ID
    except Exception:
        return WAREHOUSE_ID


def data_as_of() -> str:
    try:
        rows = run_query(
            f"SELECT date_format(from_utc_timestamp(max(order_ts), 'America/Toronto'), 'yyyy-MM-dd HH:mm') AS as_of FROM {SCHEMA}.gold_order_margin"
        )
        return f"{rows[0]['as_of']} Toronto" if rows and rows[0]["as_of"] else "no data"
    except Exception as exc:
        return f"unavailable ({type(exc).__name__})"


def format_footer(result: dict[str, Any]) -> str:
    return (
        f"Data as of {result['as_of']}  |  SQL {result['sql_ms']:,.0f} ms  |  Warehouse: {result['warehouse']}  "
        f"|  Model: {result['model']}  |  Tokens: {result['usage']['total_tokens']:,}"
    )


def _run_turn(messages: list[dict]) -> tuple[str, list[str], dict[str, int], float]:
    messages = list(messages)
    tools_used = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    stats: dict[str, float] = {"sql_ms": 0.0}
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(model=MODEL_ENDPOINT, messages=messages, tools=TOOL_SPECS, max_tokens=2000)
        if response.usage:
            for key in usage:
                usage[key] += getattr(response.usage, key, 0) or 0
        reply = response.choices[0].message
        if not reply.tool_calls:
            return reply.content or "", tools_used, usage, stats["sql_ms"]
        messages.append({"role": "assistant", "content": reply.content or "", "tool_calls": [tc.model_dump() for tc in reply.tool_calls]})
        for tc in reply.tool_calls:
            rows = call_tool(tc.function.name, json.loads(tc.function.arguments or "{}"), stats)
            tools_used.append(tc.function.name)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(rows, default=str)[:20000]})
    return "I ran out of tool calls before finishing. Try a narrower question.", tools_used, usage, stats["sql_ms"]


def ask(message: str, session_id: str) -> dict[str, Any]:
    # The full stored history is resent on every turn; nothing trims or summarizes it.
    conversation = [{"role": "system", "content": SYSTEM_PROMPT}, *load_messages(session_id), {"role": "user", "content": message}]
    attempt = 0
    while True:
        attempt += 1
        try:
            answer, tools_used, usage, sql_ms = _run_turn(conversation)
            break
        except Exception:
            if attempt >= MAX_ATTEMPTS:
                raise
    append_message(session_id, "user", message)
    append_message(session_id, "assistant", answer)
    result = {
        "answer": answer,
        "tools": tools_used,
        "attempts": attempt,
        "usage": usage,
        "sql_ms": sql_ms,
        "as_of": data_as_of(),
        "warehouse": warehouse_name(),
        "model": MODEL_ENDPOINT,
    }
    result["footer"] = format_footer(result)
    return result


def healthcheck() -> dict[str, Any]:
    steps = []

    def check(layer: str, fn) -> bool:
        try:
            steps.append({"layer": layer, "ok": True, "detail": fn()})
            return True
        except Exception as exc:
            steps.append({"layer": layer, "ok": False, "detail": str(exc)[:800]})
            return False

    check("config", lambda: {"schema": SCHEMA, "warehouse_id": WAREHOUSE_ID, "warehouse": warehouse_name(), "model": MODEL_ENDPOINT})
    model_ok = check("model", lambda: client.chat.completions.create(model=MODEL_ENDPOINT, messages=[{"role": "user", "content": "Reply with OK"}], max_tokens=5).choices[0].message.content)
    warehouse_ok = check("warehouse", lambda: run_query("SELECT 1 AS ok")[0])
    tool_ok = warehouse_ok and check("tool", lambda: f"{len(call_tool('get_orders_below_margin', {'brand': 'ACE Bakery', 'retailer': 'Costco'}))} rows")
    if model_ok and tool_ok:
        check("agent", lambda: ask(LIVE_QUESTION, "healthcheck")["answer"][:300])
    return {"ok": all(s["ok"] for s in steps) and len(steps) == 5, "steps": steps}
