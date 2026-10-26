from __future__ import annotations

import json
from datetime import datetime

DEFAULT_AS_OF = spark.sql(
    "SELECT date_format(from_utc_timestamp(current_timestamp(), 'America/Toronto'), 'yyyy-MM-dd') AS d"
).first()["d"]

dbutils.widgets.text("catalog", "serverless_nv91sa_catalog")
dbutils.widgets.text("team", "team1")
dbutils.widgets.text("as_of_date", DEFAULT_AS_OF)

catalog = dbutils.widgets.get("catalog")
team = dbutils.widgets.get("team")
as_of_date = dbutils.widgets.get("as_of_date")
schema = f"{catalog}.{team}"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.facilitator")
spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {catalog}.facilitator.answer_key (
      team STRING,
      question_id STRING,
      expected_answer_json STRING,
      computed_at TIMESTAMP
    )
    """
)

queries = {
    "Q1": f"SELECT to_json(collect_list(named_struct('customer_id', customer_id, 'customer_name', customer_name, 'open_orders', open_orders, 'avg_margin_pct', avg_margin_pct))) AS payload FROM {schema}.get_orders_below_margin('ACE Bakery', 'Costco', 0)",
    "Q2": f"SELECT to_json(named_struct('orders_today', orders_today, 'units_today', units_today, 'orders_last_week', orders_last_week, 'units_last_week', units_last_week)) AS payload FROM {schema}.get_order_velocity('ACE Bakery', 9)",
    "Q3": f"SELECT to_json(collect_list(named_struct('promo_id', promo_id, 'brand', brand, 'retailer', retailer, 'lift_pct', lift_pct, 'underperforming', underperforming))) AS payload FROM {schema}.get_active_promos(NULL)",
    "Q4": f"SELECT to_json(collect_list(named_struct('region', region, 'late_orders', late_orders))) AS payload FROM (SELECT region, COUNT(DISTINCT order_id) AS late_orders FROM {schema}.gold_order_margin WHERE is_late GROUP BY region ORDER BY late_orders DESC)",
    "Q5": f"SELECT to_json(named_struct('this_quarter', (SELECT collect_list(named_struct('customer_id', customer_id, 'revenue', revenue)) FROM {schema}.get_top_customers('Stonefire', 'this_quarter', 10)), 'last_quarter', (SELECT collect_list(named_struct('customer_id', customer_id, 'revenue', revenue)) FROM {schema}.get_top_customers('Stonefire', 'last_quarter', 10)))) AS payload",
    "Q6": f"SELECT to_json(collect_list(named_struct('retailer', retailer, 'revenue', revenue, 'avg_margin_pct', avg_margin_pct))) AS payload FROM {schema}.compare_retailers('Wonder', 'Costco', 'Walmart', 4)",
    "Q7": f"SELECT to_json(collect_list(named_struct('sku', sku, 'retailer', retailer, 'latest_wow_change_pct', latest_wow_change_pct))) AS payload FROM {schema}.get_declining_skus(3)",
    "Q8": f"SELECT to_json(collect_list(named_struct('brand', brand, 'retailer', retailer, 'revenue_vs_budget_pct', revenue_vs_budget_pct))) AS payload FROM {schema}.get_budget_vs_actual(NULL, NULL)",
    "Q9a": f"SELECT to_json(named_struct('margin_pct', ROUND(AVG(margin_pct), 2))) AS payload FROM {schema}.gold_order_margin WHERE brand = 'D''Italiano' AND retailer = 'Loblaw' AND date_trunc('month', order_ts) = date_trunc('month', current_date())",
    "Q9b": f"SELECT to_json(named_struct('margin_pct', ROUND(AVG(margin_pct), 2))) AS payload FROM {schema}.gold_order_margin WHERE brand = 'D''Italiano' AND retailer = 'Sobeys' AND date_trunc('month', order_ts) = date_trunc('month', current_date())",
    "Q9c": f"SELECT to_json(named_struct('recommended_retailer', retailer, 'avg_margin_pct', avg_margin_pct)) AS payload FROM (SELECT retailer, ROUND(AVG(margin_pct), 2) AS avg_margin_pct FROM {schema}.gold_order_margin WHERE brand = 'D''Italiano' AND retailer IN ('Loblaw', 'Sobeys') AND date_trunc('month', order_ts) = date_trunc('month', current_date()) GROUP BY retailer ORDER BY avg_margin_pct ASC LIMIT 1)",
    "Q10a": f"SELECT to_json(collect_list(named_struct('order_id', order_id, 'customer_id', customer_id, 'margin_pct', margin_pct))) AS payload FROM {schema}.get_late_orders('QC', NULL)",
    "Q10b": f"SELECT to_json(collect_list(named_struct('order_id', order_id, 'customer_id', customer_id, 'margin_pct', margin_pct))) AS payload FROM {schema}.get_late_orders('QC', 'Costco')",
    "Q10c": f"SELECT to_json(named_struct('ship_to_cust', ship_to_cust, 'buyer_name', buyer_name, 'buyer_email', buyer_email, 'buyer_phone', buyer_phone)) AS payload FROM {schema}.get_customer_contact((SELECT customer_id FROM {schema}.get_late_orders('QC', 'Costco') ORDER BY margin_pct ASC LIMIT 1))",
    "Q11": f"SELECT to_json(named_struct('ship_to_cust', ship_to_cust, 'buyer_name', buyer_name, 'buyer_email', buyer_email, 'buyer_phone', buyer_phone)) AS payload FROM {schema}.get_customer_contact((SELECT customer_id FROM {schema}.get_orders_below_margin('ACE Bakery', 'Costco', 0) ORDER BY avg_margin_pct ASC LIMIT 1))",
    "Q12": f"SELECT to_json(collect_list(named_struct('buyer_name', buyer_name, 'buyer_email', buyer_email))) AS payload FROM {schema}.silver_customers WHERE retailer = 'Walmart'",
    "Q13": f"SELECT to_json(collect_list(named_struct('customer_id', customer_id, 'avg_margin_pct', avg_margin_pct))) AS payload FROM {schema}.get_orders_below_margin('ACE Bakery', 'Costco', 5)"
}

records = []
for question_id, query in queries.items():
    payload = spark.sql(query).first()["payload"]
    records.append((team, question_id, payload or "[]", datetime.utcnow()))

answer_key_df = spark.createDataFrame(records, ["team", "question_id", "expected_answer_json", "computed_at"])
answer_key_df.createOrReplaceTempView("answer_key_updates")

spark.sql(
    f"""
    MERGE INTO {catalog}.facilitator.answer_key t
    USING answer_key_updates s
      ON t.team = s.team AND t.question_id = s.question_id
    WHEN MATCHED THEN UPDATE SET
      expected_answer_json = s.expected_answer_json,
      computed_at = s.computed_at
    WHEN NOT MATCHED THEN INSERT *
    """
)

print({"team": team, "questions": len(queries), "as_of_date": as_of_date})
