# Agent Ops War Room

FGF Brands has a sales campaign and opportunity agent that should help the marketing team answer live questions from Sales Order data. In this workshop, each team of four deploys its own copy of the stack. It works from kickoff, just badly: stale, slow, forgetful, ungoverned, and with alerts that only live in one browser tab. Each round fixes one weakness.

## Mission brief

You are on the incident response team for a customer-facing agent stack. Every layer matters:

* Lakeflow Jobs bring in new sales orders.
* Lakeflow Spark Declarative Pipelines turns landing files into gold metrics.
* UC functions are the only tools the app can call.
* The app needs memory, guardrails, and service connectivity.
* Governance and operational health must hold under pressure.

## The five rounds

* Round 1: ZeroOps triage
* Round 2: Freshness and speed with Lakehouse/real-time patterns
* Round 3: Durable memory with Lakebase
* Round 4: Governance through Unity AI Gateway
* Round 5: Durable alerting outside the browser session

Every round ends the same way: add the new component to the app as a resource in `databricks.yml`, grant the app's service principal access, and redeploy.

Every agent reply has a footer showing data as-of time, SQL ms, warehouse, model endpoint, and tokens for the turn. Watch it change as each fix lands.

## One-time setup

Do this once per team before Round 1. Pick a **driver** who runs the terminal commands; everyone else can follow in the UI.

1. Sign in to the workspace. Create a **Git folder** from `github.com/subhannita1994/fgf-agent-ops-war-room`, then use the branch picker to switch from `main` to **your team branch** (e.g. `team1`).
2. Open **SQL Warehouses** and find your team's starter warehouse (`teamN-starter`). Copy its **Warehouse ID** — your facilitator will confirm which one is yours.
3. **(Driver)** Open any notebook in the Git folder, attach to serverless, and launch the **web terminal** (bottom-right). Then:

   ```
   # from your git folder
   cd /Workspace/Users/<your-email>/fgf-agent-ops-war-room
   databricks bundle deploy --var team=<your-team> --var warehouse_id=<your-warehouse-id>
   ```

4. Confirm the deploy created **Jobs & Pipelines** → `teamN-nightly-refresh` (job) and `teamN-sales-orders` (pipeline), and **Apps** → `teamN-sales-agent` (stopped for now).
5. Run `data/00_seed_sales_orders` (all cells). Verify the pipeline ran cleanly and you see **16 tables + 1 volume** under your catalog / schema `teamN`.
6. Run `tools/01_create_uc_functions`. Verify **9 functions** appear under `teamN`.
7. Run `setup/01_grant_app` (all cells) to grant the app's service principal access to your schema.
8. **(Driver)** Back in the web terminal, start the app:

   ```
   databricks bundle run sales_agent --var team=<your-team> --var warehouse_id=<your-warehouse-id>
   ```

9. Open **Apps** → `teamN-sales-agent` (status **Running**) and click any question in the sidebar — you should get an answer with a footer. You're ready for Round 1.

## Repo map

* `data/` seeds synthetic landing data and appends daily drops.
* `pipelines/` defines the medallion pipeline.
* `tools/` creates Unity Catalog SQL functions for the agent.
* `app/` contains the Streamlit chat application.

## Ground rules

* Synthetic data only.
* Every resource is parameterized by `team` and `catalog`.
* Dates stay relative to the current Toronto date.
