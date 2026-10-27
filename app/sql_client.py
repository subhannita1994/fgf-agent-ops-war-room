from __future__ import annotations
import os, time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

_w = WorkspaceClient()

def run_query(statement: str) -> list[dict]:
    resp = _w.statement_execution.execute_statement(
        warehouse_id=os.environ["WAREHOUSE_ID"],
        statement=statement,
        wait_timeout="30s",
    )
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(0.5)
        resp = _w.statement_execution.get_statement(resp.statement_id)
    if resp.status.state != StatementState.SUCCEEDED:
        err = resp.status.error.message if resp.status.error else resp.status.state
        raise RuntimeError(f"Query failed: {err}")
    cols = [c.name for c in resp.manifest.schema.columns]
    return [dict(zip(cols, r)) for r in (resp.result.data_array or [])]
