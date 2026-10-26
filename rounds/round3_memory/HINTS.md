# Round 3 hints

## Symptom
The app can answer a first question but forgets the follow-up, especially after a restart or when traffic shifts between workers.

## Hint ladder
* Nudge: ask where conversation history lives today.
* Pointer: inspect the app's memory module and compare it with the round objective around Lakebase.
* Snippet: memory that lives only inside one Python process is not durable and is not shared.

## Genie Code starter prompt
Inspect how this app stores chat history today. Explain why multi-turn context is unreliable and what kind of durable store the round is steering teams toward.
