# Round 4 hints

## Symptom
The app can surface raw buyer PII, its model calls skip any governed path, and the "Tokens" figure in the footer climbs on every "alert me" check.

## Hint ladder
* Nudge: separate data access governance from model access governance.
* Pointer: inspect the contact function, the `model-endpoint` resource and `MODEL_ENDPOINT` in `databricks.yml`, what each alert check sends to the model, and how `ask` handles exceptions.
* Snippet: once the model sits behind a gateway with usage tracking, the usage dashboard shows the cost slope. Rate limits and guardrails go there. Finish by adding the gateway endpoint to the app as a resource (CAN QUERY), pointing `MODEL_ENDPOINT` at it, and redeploying.

## Genie Code starter prompt
Show me where this app exposes buyer PII, where the model call is wired, and why token usage grows while an alert watch is running. Explain what would need to move into a governed gateway path for this round.
