# Fault map

The app works at kickoff, just badly: stale, slow, forgetful, ungoverned, and with alerting that lives in a browser tab. Each round fixes one weakness and ends the same way: add the new component to the app as a resource in `databricks.yml`, grant the app service principal access, and redeploy (`bundle deploy`, then `bundle run sales_agent`).

Every agent reply carries a footer: `Data as of <max order_ts in gold_order_margin, Toronto> | SQL <ms> | Warehouse: <name> | Model: <endpoint> | Tokens: <total for the turn>`. That's where teams and facilitators see each fix land.

Kickoff state: the app has two resources (`sql-warehouse`, the standard warehouse with CAN USE, and `model-endpoint`, `databricks-claude-sonnet-4-6` with CAN QUERY). `setup/01_grant_app` gives its service principal USE SCHEMA, SELECT and EXECUTE on `<catalog>.<team>`. The facilitator has granted USE CATALOG to `account users`.

## Fault 1 (Round 1) — Upstream schema drift breaks silver header
* Location: `data/01_daily_drop.py`, `pipelines/sales_orders_sdp.py`
* Cause: the daily drop writes `ship_to_customer_id` instead of `ship_to_cust`. Auto Loader on `bronze_sales_order_header` evolves the schema to add the new column, so `ship_to_cust` still exists but is NULL for every daily-drop row.
* Observed symptom: the pipeline update fails on `silver_sales_order_header` with `EXPECTATION_VIOLATION(valid_ship_to)` from `@dlt.expect_or_fail("valid_ship_to", "ship_to_cust IS NOT NULL")`. It is not a missing-column / `UNRESOLVED_COLUMN` error. Because the seed rows still have `ship_to_cust`, the failure only appears after the first daily drop lands.
* Visible in the app: gold stops moving, so the footer's "Data as of" falls behind the latest daily drop.
* Intended fix: make the silver layer resilient to the renamed header column, for example `coalesce(ship_to_cust, ship_to_customer_id) AS ship_to_cust`, then let the expectation pass.

## Fault 2 (Round 2) — Stale and slow
* Location: `databricks.yml` (job schedule, app `sql-warehouse` resource), `pipelines/sales_orders_sdp.py` (gold tables), `app/sql_client.py`
* Cause, four parts:
  * The job runs once a day (`0 0 2 * * ?`, 02:00 Toronto). Its pause status comes from `schedule_pause_status`: UNPAUSED by default, PAUSED for facilitator dry runs.
  * Gold tables have no liquid clustering (`cluster_by`).
  * The app's `sql-warehouse` resource is the standard warehouse passed as `warehouse_id`.
  * `app/sql_client.py` opens a new `databricks.sql.connect(...)` per query without `use_kernel`.
* Visible in the app: an old "Data as of" time and high "SQL ms" in the footer.
* Intended fix: a fresher trigger (frequent or continuous refresh), clustering on the hot gold access patterns, `use_kernel=True` in `sql_client.py`, and a low-latency warehouse added to the app as a resource (CAN USE) with `WAREHOUSE_ID` pointed at it, then redeploy. The footer's warehouse name changes and SQL ms drops.

## Fault 3 (Round 3) — Session memory is process-local only
* Location: `app/memory.py`
* Cause: history lives in the module-level dict `conversation_store`.
* Visible in the app: multi-turn questions (Q9a-c, Q10a-c) lose context after a redeploy or app restart, or when the app runs more than one worker. "And at Sobeys?" or "Just the Costco ones" no longer resolves.
* Intended fix: a durable shared store (Lakebase) keyed by session, added to the app as a database resource, with the app service principal granted on it, then redeploy.

## Fault 4 (Round 4) — Ungoverned model calls and a cost blow-up
* Location: `databricks.yml` (`model-endpoint` resource, `MODEL_ENDPOINT` env), `app/agent.py` (`ask`, `_run_turn`), `app/main.py` (`run_alert_watch`)
* Cause, three parts:
  * The app calls the FMAPI endpoint `databricks-claude-sonnet-4-6` directly through `serving_endpoints.get_open_ai_client()`, with no gateway, usage tracking, rate limit, or guardrail.
  * "Alert me" (any question containing "alert me", such as Q1 and Q13, or the "Alert me if it gets worse" button) re-runs the full agent turn every 30 seconds, 10 times. Each check appends to the session history, and `ask` resends the whole history, so cost grows with every check. No errors are needed; it works with normal permissions.
  * `ask` retries any exception immediately, with no backoff, up to 25 times (`MAX_ATTEMPTS`).
* Visible in the app: "Tokens" in the footer climbs on every alert check. Once the model sits behind a Unity AI Gateway endpoint with usage tracking, the same climb shows up in the usage dashboard.
* Intended fix: create the team's gateway endpoint with usage tracking, rate limits and guardrails (for example, PII on buyer contacts), add it to the app as a serving endpoint resource (CAN QUERY), point `MODEL_ENDPOINT` at it, and redeploy. Optionally bound the history sent per check and add backoff to the retry. The footer's model name changes.

## Fault 5 (Round 5) — Alerting lives in the browser session
* Location: `app/main.py` (`run_alert_watch`)
* Cause: the "Alert me" loop runs inside the Streamlit script run for the session that clicked it.
* Visible in the app: closing or refreshing the tab stops the alert, and only the person who clicked sees the checks. Nobody else on the team gets notified, and nothing is recorded outside the session.
* Intended fix: move alerting out of the app into a durable, scheduled component (for example, a Databricks SQL alert or a scheduled job on the gold tables with notification destinations). Have the app create or link that alert instead of looping, add it to the app as a resource where supported, grant the app service principal, and redeploy.
