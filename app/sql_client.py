from __future__ import annotations

import os

from databricks import sql
from databricks.sdk.core import Config

_config = Config()


def run_query(statement: str) -> list[dict]:
    with sql.connect(
        server_hostname=_config.host.replace("https://", ""),
        http_path=f"/sql/1.0/warehouses/{os.environ['WAREHOUSE_ID']}",
        credentials_provider=lambda: _config.authenticate,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(statement)
            return [row.asDict() for row in cursor.fetchall()]
