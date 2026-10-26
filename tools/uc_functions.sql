CREATE OR REPLACE FUNCTION __CATALOG__.__TEAM__.get_orders_below_margin(
  brand STRING COMMENT 'Brand name, e.g. ACE Bakery',
  retailer STRING DEFAULT NULL COMMENT 'Optional retailer, e.g. Costco. NULL means all retailers.',
  max_margin_pct DOUBLE DEFAULT 0 COMMENT 'Margin threshold in percent. Locations whose margin today is below this are returned.'
)
RETURNS TABLE (
  customer_id STRING,
  customer_name STRING,
  retailer STRING,
  region STRING,
  open_orders BIGINT,
  below_threshold_lines BIGINT,
  revenue DOUBLE,
  margin_pct DOUBLE
)
COMMENT 'Customer locations with OPEN sales orders placed today (Toronto time) for a brand whose margin is below max_margin_pct. Use for below-margin, negative-margin or margin-alert questions; worst margin first.'
RETURN
WITH todays_lines AS (
  SELECT g.*, get_orders_below_margin.max_margin_pct AS threshold
  FROM __CATALOG__.__TEAM__.gold_order_margin g
  WHERE g.brand = get_orders_below_margin.brand
    AND g.status = 'OPEN'
    AND g.order_date = to_date(from_utc_timestamp(current_timestamp(), 'America/Toronto'))
    AND (get_orders_below_margin.retailer IS NULL OR g.retailer = get_orders_below_margin.retailer)
),
by_location AS (
  SELECT
    customer_id,
    customer_name,
    retailer,
    region,
    COUNT(DISTINCT order_id) AS open_orders,
    COUNT_IF(margin_pct < threshold) AS below_threshold_lines,
    ROUND(SUM(net_price), 2) AS revenue,
    ROUND(SUM(net_price * margin_pct) / SUM(net_price), 2) AS margin_pct,
    MAX(threshold) AS threshold
  FROM todays_lines
  GROUP BY customer_id, customer_name, retailer, region
)
SELECT customer_id, customer_name, retailer, region, open_orders, below_threshold_lines, revenue, margin_pct
FROM by_location
WHERE margin_pct < threshold
ORDER BY margin_pct;

CREATE OR REPLACE FUNCTION __CATALOG__.__TEAM__.get_order_velocity(
  brand STRING COMMENT 'Brand name, e.g. ACE Bakery',
  since_hour INT DEFAULT 9 COMMENT 'Hour of day in Toronto time (0-23) the window starts at, e.g. 9 for since 9am'
)
RETURNS TABLE (
  brand STRING,
  window_start_local TIMESTAMP,
  orders_today BIGINT,
  units_today DOUBLE,
  orders_same_time_last_week BIGINT,
  units_same_time_last_week DOUBLE,
  orders_change_pct DOUBLE
)
COMMENT 'Order count and units for a brand from since_hour today (Toronto time) until now, compared with the same window exactly 7 days ago. Use for since-9am / so-far-today / vs last week questions.'
RETURN
WITH b AS (
  SELECT
    to_utc_timestamp(make_timestamp(year(t), month(t), day(t), get_order_velocity.since_hour, 0, 0), 'America/Toronto') AS start_ts,
    make_timestamp(year(t), month(t), day(t), get_order_velocity.since_hour, 0, 0) AS start_local,
    current_timestamp() AS end_ts
  FROM (SELECT from_utc_timestamp(current_timestamp(), 'America/Toronto') AS t)
),
m AS (
  SELECT
    COUNT(DISTINCT CASE WHEN g.order_ts BETWEEN b.start_ts AND b.end_ts THEN g.order_id END) AS orders_today,
    SUM(CASE WHEN g.order_ts BETWEEN b.start_ts AND b.end_ts THEN g.qty END) AS units_today,
    COUNT(DISTINCT CASE WHEN g.order_ts BETWEEN b.start_ts - INTERVAL 7 DAYS AND b.end_ts - INTERVAL 7 DAYS THEN g.order_id END) AS orders_lw,
    SUM(CASE WHEN g.order_ts BETWEEN b.start_ts - INTERVAL 7 DAYS AND b.end_ts - INTERVAL 7 DAYS THEN g.qty END) AS units_lw,
    MAX(b.start_local) AS start_local
  FROM __CATALOG__.__TEAM__.gold_order_margin g
  CROSS JOIN b
  WHERE g.brand = get_order_velocity.brand
    AND g.status <> 'CANCELLED'
)
SELECT
  get_order_velocity.brand,
  start_local,
  orders_today,
  coalesce(units_today, 0),
  orders_lw,
  coalesce(units_lw, 0),
  ROUND((orders_today / NULLIF(orders_lw, 0) - 1) * 100, 1)
FROM m;

CREATE OR REPLACE FUNCTION __CATALOG__.__TEAM__.get_active_promos(
  brand STRING DEFAULT NULL COMMENT 'Optional brand filter. NULL means all brands.'
)
RETURNS TABLE (
  promo_id STRING,
  brand STRING,
  retailer STRING,
  promo_type STRING,
  start_date DATE,
  end_date DATE,
  discount_pct DOUBLE,
  lift_pct DOUBLE,
  underperforming BOOLEAN
)
COMMENT 'Promotions active today with unit lift vs the prior 4-week daily baseline, one row per promo and retailer. underperforming = lift below 5 percent. Use for active promo, end-cap, flyer, TPD and lift questions.'
RETURN
SELECT
  p.promo_id,
  p.brand,
  p.retailer,
  p.promo_type,
  p.start_date,
  p.end_date,
  p.discount_pct,
  p.lift_pct,
  coalesce(p.lift_pct, 0) < 5 AS underperforming
FROM __CATALOG__.__TEAM__.gold_promo_performance p
WHERE p.is_active
  AND (get_active_promos.brand IS NULL OR p.brand = get_active_promos.brand)
ORDER BY underperforming DESC, p.lift_pct;

CREATE OR REPLACE FUNCTION __CATALOG__.__TEAM__.get_late_orders(
  region STRING DEFAULT NULL COMMENT 'Optional region: ON, QC, BC, AB or Atlantic',
  retailer STRING DEFAULT NULL COMMENT 'Optional retailer, e.g. Costco'
)
RETURNS TABLE (
  order_id STRING,
  customer_id STRING,
  customer_name STRING,
  retailer STRING,
  region STRING,
  requested_delivery_date DATE,
  days_late INT,
  order_value DOUBLE
)
COMMENT 'OPEN orders past their requested delivery date, one row per order, most days late first. Filter by region and/or retailer. Count rows by region to rank regions by late orders.'
RETURN
SELECT
  g.order_id,
  g.customer_id,
  g.customer_name,
  g.retailer,
  g.region,
  g.requested_delivery_date,
  datediff(to_date(from_utc_timestamp(current_timestamp(), 'America/Toronto')), g.requested_delivery_date) AS days_late,
  ROUND(SUM(g.net_price), 2) AS order_value
FROM __CATALOG__.__TEAM__.gold_order_margin g
WHERE g.status = 'OPEN'
  AND g.requested_delivery_date < to_date(from_utc_timestamp(current_timestamp(), 'America/Toronto'))
  AND (get_late_orders.region IS NULL OR g.region = get_late_orders.region)
  AND (get_late_orders.retailer IS NULL OR g.retailer = get_late_orders.retailer)
GROUP BY ALL
ORDER BY days_late DESC, order_value DESC;

CREATE OR REPLACE FUNCTION __CATALOG__.__TEAM__.get_top_customers(
  brand STRING COMMENT 'Brand name, e.g. Stonefire',
  period STRING DEFAULT 'this_quarter' COMMENT 'Either this_quarter (quarter to date) or last_quarter',
  n INT DEFAULT 10 COMMENT 'Number of customers to return'
)
RETURNS TABLE (
  rank INT,
  customer_id STRING,
  customer_name STRING,
  retailer STRING,
  revenue DOUBLE,
  orders BIGINT
)
COMMENT 'Top n customer locations by net revenue for a brand in this_quarter (to date) or last_quarter. Call once per period to compare quarters.'
RETURN
WITH q AS (
  SELECT date_trunc('quarter', to_date(from_utc_timestamp(current_timestamp(), 'America/Toronto'))) AS this_q
),
ranked AS (
  SELECT
    g.customer_id,
    g.customer_name,
    g.retailer,
    ROUND(SUM(g.net_price), 2) AS revenue,
    COUNT(DISTINCT g.order_id) AS orders,
    ROW_NUMBER() OVER (ORDER BY SUM(g.net_price) DESC) AS rn
  FROM __CATALOG__.__TEAM__.gold_order_margin g
  CROSS JOIN q
  WHERE g.brand = get_top_customers.brand
    AND g.status <> 'CANCELLED'
    AND g.order_date >= CASE WHEN get_top_customers.period = 'last_quarter' THEN add_months(q.this_q, -3) ELSE q.this_q END
    AND g.order_date < CASE WHEN get_top_customers.period = 'last_quarter' THEN q.this_q ELSE add_months(q.this_q, 3) END
  GROUP BY g.customer_id, g.customer_name, g.retailer
)
SELECT CAST(rn AS INT), customer_id, customer_name, retailer, revenue, orders
FROM ranked
WHERE rn <= get_top_customers.n
ORDER BY rn;

CREATE OR REPLACE FUNCTION __CATALOG__.__TEAM__.compare_retailers(
  brand STRING COMMENT 'Brand name, e.g. Wonder',
  retailer_a STRING COMMENT 'First retailer, e.g. Costco',
  retailer_b STRING COMMENT 'Second retailer, e.g. Walmart. Pass the same value as retailer_a to look at one retailer.',
  weeks INT DEFAULT 4 COMMENT 'Trailing number of weeks. Ignored when month_to_date is true.',
  month_to_date BOOLEAN DEFAULT FALSE COMMENT 'true = use the current calendar month instead of trailing weeks'
)
RETURNS TABLE (
  retailer STRING,
  revenue DOUBLE,
  units DOUBLE,
  margin_pct DOUBLE,
  orders BIGINT
)
COMMENT 'Side-by-side net revenue, units and revenue-weighted margin percent for one brand at two retailers, over trailing weeks or month to date. Use for margin or revenue comparisons between retailers.'
RETURN
SELECT
  g.retailer,
  ROUND(SUM(g.net_price), 2) AS revenue,
  SUM(g.qty) AS units,
  ROUND(SUM(g.net_price * g.margin_pct) / SUM(g.net_price), 2) AS margin_pct,
  COUNT(DISTINCT g.order_id) AS orders
FROM __CATALOG__.__TEAM__.gold_order_margin g
WHERE g.brand = compare_retailers.brand
  AND g.retailer IN (compare_retailers.retailer_a, compare_retailers.retailer_b)
  AND g.status <> 'CANCELLED'
  AND g.order_date >= CASE
    WHEN compare_retailers.month_to_date THEN trunc(to_date(from_utc_timestamp(current_timestamp(), 'America/Toronto')), 'MM')
    ELSE date_sub(to_date(from_utc_timestamp(current_timestamp(), 'America/Toronto')), compare_retailers.weeks * 7)
  END
GROUP BY g.retailer
ORDER BY g.retailer;

CREATE OR REPLACE FUNCTION __CATALOG__.__TEAM__.get_declining_skus(
  weeks INT DEFAULT 3 COMMENT 'Number of consecutive completed weeks that must each show a week-over-week revenue decline'
)
RETURNS TABLE (
  sku STRING,
  brand STRING,
  retailer STRING,
  weeks_declining BIGINT,
  latest_week_start DATE,
  latest_week_revenue DOUBLE,
  latest_wow_change_pct DOUBLE,
  cumulative_change_pct DOUBLE,
  weekly_revenue_lost DOUBLE
)
COMMENT 'SKU and retailer combinations whose weekly net revenue fell week over week in each of the last N completed weeks (Mon-Sun, current partial week excluded). Largest weekly revenue lost first.'
RETURN
WITH ranked AS (
  SELECT
    w.*,
    ROW_NUMBER() OVER (PARTITION BY w.sku, w.retailer ORDER BY w.week_start DESC) AS rn
  FROM __CATALOG__.__TEAM__.gold_sales_weekly w
  WHERE w.week_start < date_trunc('week', to_date(from_utc_timestamp(current_timestamp(), 'America/Toronto')))
)
SELECT
  sku,
  brand,
  retailer,
  COUNT(*) AS weeks_declining,
  MAX(week_start) AS latest_week_start,
  MAX_BY(revenue, week_start) AS latest_week_revenue,
  MAX_BY(wow_change_pct, week_start) AS latest_wow_change_pct,
  ROUND((EXP(SUM(LN(1 + wow_change_pct / 100))) - 1) * 100, 1) AS cumulative_change_pct,
  ROUND(MIN_BY(revenue / (1 + wow_change_pct / 100), week_start) - MAX_BY(revenue, week_start), 2) AS weekly_revenue_lost
FROM ranked
WHERE rn <= get_declining_skus.weeks
GROUP BY sku, brand, retailer
HAVING COUNT(*) = get_declining_skus.weeks AND MAX(wow_change_pct) < 0
ORDER BY weekly_revenue_lost DESC;

CREATE OR REPLACE FUNCTION __CATALOG__.__TEAM__.get_budget_vs_actual(
  brand STRING DEFAULT NULL COMMENT 'Optional brand filter',
  retailer STRING DEFAULT NULL COMMENT 'Optional retailer filter'
)
RETURNS TABLE (
  brand STRING,
  retailer STRING,
  actual_revenue DOUBLE,
  budget_revenue DOUBLE,
  revenue_gap DOUBLE,
  revenue_vs_budget_pct DOUBLE,
  actual_units DOUBLE,
  budget_units BIGINT,
  units_vs_budget_pct DOUBLE
)
COMMENT 'Current calendar month (Toronto) actual vs budget revenue and units by brand and retailer. Negative revenue_vs_budget_pct means behind budget. Furthest behind first.'
RETURN
SELECT
  b.brand,
  b.retailer,
  b.actual_revenue,
  b.budget_revenue,
  b.revenue_gap,
  b.revenue_vs_budget_pct,
  b.actual_units,
  b.budget_units,
  b.units_vs_budget_pct
FROM __CATALOG__.__TEAM__.gold_budget_vs_actual b
WHERE b.month = trunc(to_date(from_utc_timestamp(current_timestamp(), 'America/Toronto')), 'MM')
  AND (get_budget_vs_actual.brand IS NULL OR b.brand = get_budget_vs_actual.brand)
  AND (get_budget_vs_actual.retailer IS NULL OR b.retailer = get_budget_vs_actual.retailer)
ORDER BY b.revenue_vs_budget_pct;

CREATE OR REPLACE FUNCTION __CATALOG__.__TEAM__.get_customer_contact(
  customer_id STRING COMMENT 'Ship-to customer id, e.g. C0001, as returned by the other tools'
)
RETURNS TABLE (
  customer_id STRING,
  customer_name STRING,
  retailer STRING,
  buyer_name STRING,
  buyer_email STRING,
  buyer_phone STRING
)
COMMENT 'Buyer name, email and phone for one ship-to customer location. Call once per customer when the user asks who the buyer is or wants contact details.'
RETURN
SELECT
  c.ship_to_cust,
  c.customer_name,
  c.retailer,
  c.buyer_name,
  c.buyer_email,
  c.buyer_phone
FROM __CATALOG__.__TEAM__.silver_customers c
WHERE c.ship_to_cust = get_customer_contact.customer_id;
