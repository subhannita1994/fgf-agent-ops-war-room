# Round 1 hints

## Symptom
The live question is stale or broken, and the first place to start is figuring out which layer is currently red.

## Hint ladder
* Nudge: check operational health before changing code.
* Pointer: look at monitoring, the latest job run, and the latest pipeline update.
* Snippet: trace the path in order — landing files, daily job, pipeline refresh, then gold table freshness.

## Genie Code starter prompt
Help me triage this stack from the outside in. Start with the latest job and pipeline health, then tell me which layer is broken first.
