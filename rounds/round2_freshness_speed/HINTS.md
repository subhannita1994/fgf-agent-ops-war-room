# Round 2 hints

## Symptom
Fresh data lands, but the agent still feels stale or slow when it answers live questions.

## Hint ladder
* Nudge: compare how often data arrives with how often downstream tables refresh.
* Pointer: inspect the job schedule, the pipeline gold definitions, and the warehouse path used by the app.
* Snippet: live questions usually need a fresher trigger, optimized gold layout, and a low-latency serving warehouse.

## Genie Code starter prompt
Review the data freshness path and query path for this repo. Show me what makes the agent stale or slow without changing anything yet.
