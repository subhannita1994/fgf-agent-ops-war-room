from __future__ import annotations

import os
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Disposition, Format, StatementState

_w = WorkspaceClient()


def run_query(statement: str) -> list[dict]:
    # Ask for JSON rows explicitly. Without this, real-time warehouses (e.g. team0-rt) return the
    # result as an inline Arrow attachment, data_array is None, and every query looks empty.
    resp = _w.statement_execution.execute_statement(
        warehouse_id=os.environ["WAREHOUSE_ID"],
        statement=statement,
        wait_timeout="30s",
        format=Format.JSON_ARRAY,
        disposition=Disposition.INLINE,
    )
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(0.5)
        resp = _w.statement_execution.get_statement(resp.statement_id)
    if resp.status.state != StatementState.SUCCEEDED:
        err = resp.status.error.message if resp.status.error else resp.status.state
        raise RuntimeError(f"Query failed: {err}")

    cols = [c.name for c in resp.manifest.schema.columns]
    rows: list[list] = []
    chunk = resp.result
    while chunk is not None:
        rows.extend(chunk.data_array or [])
        if chunk.next_chunk_index is None:
            break
        chunk = _w.statement_execution.get_statement_result_chunk_n(resp.statement_id, chunk.next_chunk_index)
    return [dict(zip(cols, r)) for r in rows]
