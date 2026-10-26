# Round 5 hints

## Symptom
"Alert me" works while you watch, but close or refresh the tab and the alert stops. Only the person who clicked ever sees it.

## Hint ladder
* Nudge: ask where the alert loop actually runs, and who it runs for.
* Pointer: inspect `run_alert_watch` in `app/main.py` and think about what in the platform already evaluates a query on a schedule and notifies people.
* Snippet: a durable alert lives outside the app, runs on a schedule against gold, and notifies a destination. The app only needs to create or link it. Finish by adding what the app needs as a resource, granting the app service principal, and redeploying.

## Genie Code starter prompt
Explain where the app's "Alert me" loop runs and why it stops when the browser closes. Propose a durable replacement for Q13 that keeps working with no one watching.
