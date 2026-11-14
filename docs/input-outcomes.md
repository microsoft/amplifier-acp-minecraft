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
- `work_resumptions`: up to 16 saved resumption receipts linked to this exact
  source, with `task_id`, `recorded_status`, `scheduled`, and `execution_started`.
  These describe the saved result, not current task status. For example,
  `scheduled: true, execution_started: false` means work was scheduled to resume;
  it does not prove physical execution or completion. `conversation_only` still
  describes the original input admission and must not override this later result.
  `work_resumptions_omitted` marks a bounded or incomplete projection. Older
  servers may omit these fields; absence is not proof that no resumption occurred.
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

## Optional host source receipts

An ACP host may advertise the source-delivery profile in
`_meta["io.github.bkrabach.agent-instance"].inputContinuity.sourceDelivery`.
Minecraft uses ordinary-prompt metadata only with exact version 1,
`metadata: "com.microsoft.amplifier.source-delivery"`,
`receiptsMethod: "_amplifier/source_receipts"`, `ordinaryPrompts: true` and
`promptRetry: "inspectOnly"`. Plain ACP remains supported without that profile.

For an admitted public input whose complete original `source_fact` set is
available, the controller sends original IDs, revisions and occurrence times
alongside any existing attention offer. It records the input ID and original
endpoint/session binding in the existing awareness journal before dispatch.
Continuations, legacy private inputs and incomplete source sets do not acquire
invented source metadata. A retained dispatch cannot escape inspection by losing
its metadata or by downgrading host capabilities.

A lost reply is inspection-only on the original loaded session. Reordering or
splitting the same retained source set cannot create another send. Only a fresh,
exact host `notAccepted` or `promptRequired` receipt with explicit
`incorporated: false` can promote a previously steered input to its first ordinary
prompt, using that same input ID and source set. Missing legacy binding, changed
binding, unavailable evidence or an earlier ordinary dispatch does not qualify.
This is not a replay queue or an automatic retry policy. Both local journal and
host retention remain bounded; absence does not establish non-delivery.

With `workReferences: true`, the journal also retains host work references and
coverage separately from delivery facts. A host's proposed or accepted work
record does not accept, amend, resume or complete a Minecraft task. Delivery
receipt correlation requires the original input ID; work references are scoped
to the exact original source revision and may survive delivery-record eviction.
Missing/malformed work evidence is `coverage: "unknown"`, not proof of no work.
The body remains authoritative for task bounds, Stop and physical effects;
`completion` remains `not_established`. No host work record is created by this
integration, and these private receipt details are not posted into public chat.
