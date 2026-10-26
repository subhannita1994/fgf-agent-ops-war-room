import dlt
from pyspark.sql import Window
from pyspark.sql import functions as F

catalog = spark.conf.get("catalog")
team = spark.conf.get("team")
landing = f"/Volumes/{catalog}/{team}/landing"
TZ = "America/Toronto"


def local_today():
    return F.to_date(F.from_utc_timestamp(F.current_timestamp(), TZ))


def bronze(folder: str):
    @dlt.table(name=f"bronze_{folder}", comment=f"Raw {folder} files from the landing volume.")
    def _bronze():
        return (
            spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "json")
            .option("cloudFiles.inferColumnTypes", "true")
            .load(f"{landing}/{folder}")
            .withColumn("_ingested_at", F.current_timestamp())
        )


for folder in ["products", "customers", "promotions", "budget", "sales_order_header", "sales_order_lines"]:
    bronze(folder)


@dlt.table(comment="Product master.")
def silver_products():
    return spark.read.table("bronze_products").select(
        "sku",
        "brand",
        "category",
        "pack_size",
        F.col("list_price").cast("double").alias("list_price"),
        F.col("standard_cost").cast("double").alias("standard_cost"),
    )


@dlt.table(comment="Ship-to customer locations, including buyer contact details.")
def silver_customers():
    return spark.read.table("bronze_customers").select(
        "ship_to_cust", "customer_name", "retailer", "region", "channel", "buyer_name", "buyer_email", "buyer_phone"
    )


@dlt.table(comment="Trade promotions.")
def silver_promotions():
    return spark.read.table("bronze_promotions").select(
        "promo_id",
        "brand",
        "sku",
        "retailer",
        "promo_type",
        F.col("start_date").cast("date").alias("start_date"),
        F.col("end_date").cast("date").alias("end_date"),
        F.col("discount_pct").cast("double").alias("discount_pct"),
    )


@dlt.table(comment="Monthly budget by brand and retailer.")
def silver_budget():
    return spark.read.table("bronze_budget").select(
        "brand",
        "retailer",
        F.col("month").cast("date").alias("month"),
        F.col("budget_revenue").cast("double").alias("budget_revenue"),
        F.col("budget_units").cast("bigint").alias("budget_units"),
    )


@dlt.table(comment="Sales order headers.")
@dlt.expect("valid_order_id", "order_id IS NOT NULL")
@dlt.expect_or_fail("valid_ship_to", "ship_to_cust IS NOT NULL")
def silver_sales_order_header():
    return spark.read.table("bronze_sales_order_header").select(
        "order_id",
        F.col("order_ts").cast("timestamp").alias("order_ts"),
        "ship_to_cust",
        "status",
        F.col("requested_delivery_date").cast("date").alias("requested_delivery_date"),
        F.col("actual_ship_date").cast("date").alias("actual_ship_date"),
    )


@dlt.table(comment="Sales order lines.")
def silver_sales_order_lines():
    return spark.read.table("bronze_sales_order_lines").select(
        "order_id",
        F.col("line_no").cast("int").alias("line_no"),
        "sku",
        F.col("qty").cast("double").alias("qty"),
        F.col("unit_price").cast("double").alias("unit_price"),
        F.col("discount_amt").cast("double").alias("discount_amt"),
        "promo_id",
    )


@dlt.table(comment="One row per order line with net price, margin, promo and lateness flags.")
def gold_order_margin():
    h = spark.read.table("silver_sales_order_header")
    l = spark.read.table("silver_sales_order_lines")
    p = spark.read.table("silver_products")
    c = spark.read.table("silver_customers")
    net = F.col("l.unit_price") * F.col("l.qty") - F.col("l.discount_amt")
    cost = F.col("p.standard_cost") * F.col("l.qty")
    return (
        h.alias("h")
        .join(l.alias("l"), "order_id")
        .join(p.alias("p"), F.col("l.sku") == F.col("p.sku"))
        .join(c.alias("c"), F.col("h.ship_to_cust") == F.col("c.ship_to_cust"))
        .select(
            "order_id",
            F.col("h.order_ts").alias("order_ts"),
            F.to_date(F.from_utc_timestamp("h.order_ts", TZ)).alias("order_date"),
            F.col("h.status").alias("status"),
            F.col("h.requested_delivery_date").alias("requested_delivery_date"),
            F.col("c.ship_to_cust").alias("customer_id"),
            F.col("c.customer_name").alias("customer_name"),
            F.col("c.retailer").alias("retailer"),
            F.col("c.region").alias("region"),
            F.col("l.line_no").alias("line_no"),
            F.col("l.sku").alias("sku"),
            F.col("p.brand").alias("brand"),
            F.col("l.qty").alias("qty"),
            F.round(net, 2).alias("net_price"),
            F.when(net == 0, F.lit(0.0)).otherwise(F.round((net - cost) / net * 100, 2)).alias("margin_pct"),
            F.col("l.promo_id").isNotNull().alias("is_promo"),
            F.col("l.promo_id").alias("promo_id"),
            ((F.col("h.status") == "OPEN") & (F.col("h.requested_delivery_date") < local_today())).alias("is_late"),
        )
    )


@dlt.table(comment="Promotion x retailer: daily units during the promo vs the prior 4-week baseline.")
def gold_promo_performance():
    pr = spark.read.table("silver_promotions").alias("pr")
    gm = spark.read.table("gold_order_margin").where("status <> 'CANCELLED'").alias("gm")
    today = local_today()
    promo_end = F.least(F.col("pr.end_date"), today)
    in_promo = F.col("gm.order_date").between(F.col("pr.start_date"), promo_end)
    in_base = F.col("gm.order_date").between(F.date_sub("pr.start_date", 28), F.date_sub("pr.start_date", 1))
    joined = pr.join(
        gm,
        (F.col("gm.brand") == F.col("pr.brand"))
        & (F.col("pr.sku").isNull() | (F.col("gm.sku") == F.col("pr.sku")))
        & (F.col("pr.retailer").isNull() | (F.col("gm.retailer") == F.col("pr.retailer"))),
    )
    agg = joined.groupBy(
        "pr.promo_id", "pr.brand", "pr.sku", "pr.promo_type", "pr.start_date", "pr.end_date", "pr.discount_pct", F.col("gm.retailer").alias("retailer")
    ).agg(
        F.sum(F.when(in_promo, F.col("gm.qty")).otherwise(0)).alias("promo_units"),
        F.sum(F.when(in_base, F.col("gm.qty")).otherwise(0)).alias("baseline_units"),
        F.sum(F.when(in_promo, F.col("gm.net_price")).otherwise(0)).alias("promo_revenue"),
        (F.datediff(promo_end, F.col("pr.start_date")) + 1).alias("promo_days"),
    )
    daily_promo = F.col("promo_units") / F.col("promo_days")
    daily_base = F.col("baseline_units") / 28
    return agg.select(
        "*",
        F.when((F.col("promo_days") > 0) & (F.col("baseline_units") > 0), F.round((daily_promo / daily_base - 1) * 100, 2)).alias("lift_pct"),
        today.between(F.col("start_date"), F.col("end_date")).alias("is_active"),
    )


@dlt.table(comment="SKU x retailer x week revenue, units, margin and week-over-week change.")
def gold_sales_weekly():
    weekly = (
        spark.read.table("gold_order_margin")
        .where("status <> 'CANCELLED'")
        .groupBy("sku", "brand", "retailer", F.date_trunc("week", "order_date").cast("date").alias("week_start"))
        .agg(
            F.round(F.sum("net_price"), 2).alias("revenue"),
            F.sum("qty").alias("units"),
            F.round(F.avg("margin_pct"), 2).alias("avg_margin"),
        )
    )
    prev = F.lag("revenue").over(Window.partitionBy("sku", "retailer").orderBy("week_start"))
    return weekly.withColumn("wow_change_pct", F.round((F.col("revenue") - prev) / prev * 100, 2))


@dlt.table(comment="Brand x retailer x month actual vs budget revenue and units.")
def gold_budget_vs_actual():
    actuals = (
        spark.read.table("gold_order_margin")
        .where("status <> 'CANCELLED'")
        .groupBy("brand", "retailer", F.trunc("order_date", "MM").alias("month"))
        .agg(F.sum("net_price").alias("actual_revenue"), F.sum("qty").alias("actual_units"))
    )
    b = spark.read.table("silver_budget")
    return b.join(actuals, ["brand", "retailer", "month"], "left").select(
        "brand",
        "retailer",
        "month",
        F.round("actual_revenue", 2).alias("actual_revenue"),
        "actual_units",
        "budget_revenue",
        "budget_units",
        F.round(F.col("actual_revenue") - F.col("budget_revenue"), 2).alias("revenue_gap"),
        F.round((F.col("actual_revenue") / F.col("budget_revenue") - 1) * 100, 2).alias("revenue_vs_budget_pct"),
        F.round((F.col("actual_units") / F.col("budget_units") - 1) * 100, 2).alias("units_vs_budget_pct"),
    )

