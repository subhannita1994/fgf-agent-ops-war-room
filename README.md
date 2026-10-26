# Agent Ops War Room

FGF Brands has a sales campaign and opportunity agent that should help the marketing team answer live questions from Sales Order data. In this workshop, each team of four deploys its own copy of the stack. It works from kickoff, just badly: stale, slow, forgetful, ungoverned, and with alerts that only live in one browser tab. Each round fixes one weakness.

## Mission brief

You are on the incident response team for a customer-facing agent stack. Every layer matters:

* Lakeflow Jobs bring in new sales orders.
* Lakeflow Spark Declarative Pipelines turns landing files into gold metrics.
* UC functions are the only tools the app can call.
* The app needs memory, guardrails, and service connectivity.
* Governance and operational health must hold under pressure.

## The live question

Start with:

* Which customers have open sales orders for ACE Bakery below margin right now, during today's promo — and alert me if it gets worse.

Then work forward through the rest of [QUESTIONS.md](./QUESTIONS.md).

## The five rounds

* Round 1: ZeroOps triage
* Round 2: Freshness and speed with Lakehouse/real-time patterns
* Round 3: Durable memory with Lakebase
* Round 4: Governance through Unity AI Gateway
* Round 5: Durable alerting outside the browser session

Every round ends the same way: add the new component to the app as a resource in `databricks.yml`, grant the app's service principal access, and redeploy.

Every agent reply has a footer showing data as-of time, SQL ms, warehouse, model endpoint, and tokens for the turn. Watch it change as each fix lands.

## Deploy your stack

1. Open the web terminal in your team branch of this Git folder.
2. Deploy the bundle:
   `databricks bundle deploy --var team=<your-team> --var warehouse_id=<warehouse-id>`
   Your facilitator gives you the warehouse ID. Add `--var catalog=<catalog>` if your workshop catalog is not the default.
3. Run `data/00_seed_sales_orders` (whoever runs it owns the team schema).
4. Run `tools/01_create_uc_functions`.
5. Run `setup/01_grant_app`. It grants the app's service principal USE SCHEMA, SELECT and EXECUTE on your schema. Run it as the schema owner from step 3 (or someone with MANAGE on the schema).
6. Start the app: `databricks bundle run sales_agent --var team=<your-team> --var warehouse_id=<warehouse-id>`
7. Run the job `<your-team>-nightly-refresh`, then ask the app Q1.

## Repo map

* `data/` seeds synthetic landing data and appends daily drops.
* `pipelines/` defines the medallion pipeline.
* `tools/` creates Unity Catalog SQL functions for the agent.
* `app/` contains the Streamlit chat application.
* `checks/` contains round validation notebooks.
* `rounds/` contains hints for each repair round.
* `facilitator/` contains the hidden answer key and fault documentation.

## Ground rules

* Synthetic data only.
* Every resource is parameterized by `team` and `catalog`.
* Dates stay relative to the current Toronto date.
* Teams should not look in `facilitator/` during the workshop.
