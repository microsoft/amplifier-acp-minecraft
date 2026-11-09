# Inspecting the outcome of a queued input

Private clients can discover `input_outcomes` on authenticated `GET /status`:

```json
{"version":1,"method":"GET","path":"/input-outcomes","max_ids":16}
```

Only use the advertised version and route. Query one to sixteen distinct original
queue UUIDs with `GET /input-outcomes?ids=<uuid>,<uuid>`. Use the installation's
private control token, never its public presence credential. Lookup does not
start a model, consume input, change tasks, or perform world actions.

The response contains `version`, `observed_at`, and `outcomes`. Each outcome has:

- `request_id` and `delivery`: `queued`, `admitted`, `terminal`, `interrupted`, or
  `unknown`. Admission proves a body turn reserved the input, not that the model
  incorporated it. Terminal proves that turn ended, not successful fulfillment.
- `admitted_at`, `terminal_at`, `conversation_only`, `turn_task_id`, and
  `blocked_reason`: captured facts, or null. A later task cannot rewrite these.
- `source_ids`: the complete co-admitted source set, when retained. A response
  belongs to that turn; it is not an individual completion for each source.
- `responses`: up to 32 retained public transport submissions with durable event
  `id`, `at`, `text`, and `audience: "public"`. These are not recipient acknowledgments.
  `responses_omitted` indicates earlier packets were dropped from this bounded view, or an invalid oversized
  non-packet record was omitted. Emitted packet text is never clipped.
- `task_authorizations`: exact `accept`/`amend` receipts linked to this source,
  with `task_id` and `authority_revision`. These do not prove execution.
- `completion: "not_established"`: this endpoint does not certify requested work.

Private response text is intentionally withheld. `private_responses_withheld`
may be true; the private owner journal is unchanged. There is no caller identity
binding on this lookup, so an installation control credential alone must not be
used to publish private responses to another conversation. Consumers must also
retain their original call/caller/audience association for queried queue IDs.
Original input text is never returned by this endpoint.

The installation retains at most 500 admitted outcomes, including active inputs,
without extending source lifetimes. Restart interrupts an unfinished retained
turn; Stop also records interruption. Lookup of an older admission without a
retained terminal returns `admitted` with `reason: "terminal_not_retained"`.
Missing/evicted evidence returns `unknown` with `reason: "not_retained"`.
Neither case permits replay. Queued state is read from the existing live inbox.
This evidence is not added to model context or public presence.
