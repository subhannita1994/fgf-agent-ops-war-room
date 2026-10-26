from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TORONTO = ZoneInfo("America/Toronto")
DEFAULT_AS_OF = spark.sql(
    "SELECT date_format(from_utc_timestamp(current_timestamp(), 'America/Toronto'), 'yyyy-MM-dd') AS d"
).first()["d"]

parser = argparse.ArgumentParser()
parser.add_argument("--catalog", default="serverless_nv91sa_catalog")
parser.add_argument("--team", default="team1")
parser.add_argument("--as_of_date", default=DEFAULT_AS_OF)
args, _ = parser.parse_known_args()

catalog = args.catalog
team = args.team
as_of_date = datetime.strptime(args.as_of_date, "%Y-%m-%d").date()
volume_root = Path(f"/Volumes/{catalog}/{team}/landing")
random.seed(datetime.now(TORONTO).strftime("%Y%m%d%H%M"))

customers = spark.read.json(str(volume_root / "customers")).filter("retailer = 'Costco'").select("ship_to_cust").limit(20).collect()
products = spark.read.json(str(volume_root / "products")).filter("brand = 'ACE Bakery'").select("sku", "standard_cost", "list_price").collect()

now = datetime.now(TORONTO)
headers = []
lines = []
for idx in range(1, 26):
    customer = random.choice(customers)
    product = random.choice(products)
    order_id = f"DROP-{now.strftime('%Y%m%d%H%M%S')}-{idx:03d}"
    requested_delivery = (as_of_date + timedelta(days=1)).isoformat()
    headers.append(
        {
            "order_id": order_id,
            "order_ts": now.isoformat(),
            "ship_to_customer_id": customer["ship_to_cust"],
            "status": "OPEN",
            "requested_delivery_date": requested_delivery,
            "actual_ship_date": None,
        }
    )
    qty = random.randint(16, 48)
    unit_price = round(float(product["standard_cost"]) * random.uniform(0.8, 0.94), 2)
    lines.append(
        {
            "order_id": order_id,
            "line_no": 1,
            "sku": product["sku"],
            "qty": qty,
            "unit_price": unit_price,
            "discount_amt": round((float(product["list_price"]) - unit_price) * qty, 2),
            "promo_id": "PROMO-ACE-COSTCO-ACTIVE",
        }
    )

header_file = volume_root / "sales_order_header" / f"daily_drop_{now.strftime('%Y%m%d%H%M%S')}.json"
line_file = volume_root / "sales_order_lines" / f"daily_drop_{now.strftime('%Y%m%d%H%M%S')}.json"
for file_path, rows in [(header_file, headers), (line_file, lines)]:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str) + "\n")

print({"headers_added": len(headers), "lines_added": len(lines), "written_at": now.isoformat()})
