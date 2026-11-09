# Installation caller inputs and outcomes

An optional dedicated installation credential lets an authorized voice or other
local client submit original human text and read only the outcome associated
with that exact source. This is a Minecraft HTTP boundary, not an ACP extension
or a Minecraft player identity. Legacy owner `/task` calls remain unchanged.

Configure `installation_callers` in the private body configuration as an array
of `{id,label,token}`. IDs and tokens must be unique; tokens must contain at
least 32 URL-safe alphanumeric, underscore or hyphen characters and differ from the body, context and presence credentials.
Use a generated secret and installation-owned private distribution. This gives
the caller human-input ingress, not maintenance, world tools or journal access.
The caller must independently authorize the current human, agent and connection.
Never expose this credential to a browser or include it in a repository.

The dedicated bearer token can access only:

- `GET /source-capabilities`: version 1, submission and outcome method/path.
- `POST /task`: exact `{text,source}` below.
- `POST /source-outcomes`: exact source-scoped query below.

The owner `/status` also advertises `installation_inputs`. Parent support does
not enroll a credential or enable any task/activity policy. No endpoint accepts
browser-origin requests. The normal loopback/container route restrictions apply.

```json
{
  "text": "The unchanged original human wording",
  "source": {
    "version": 1,
    "request_id": "87ca622b-3360-4694-a8c6-f0ebd4c522e7",
    "call_id": "original-call-id",
    "intent_id": "original-intent-id",
    "revision": "original-revision",
    "occurred_at": "2026-11-09T16:00:00.000Z",
    "actor": {"id": "asserted-human-id", "label": "Human label"},
    "audience": {"kind": "private", "experience": "voice-client", "id": "original-audience-id"}
  }
}
```

The credential establishes the caller installation. Actor identity is asserted
by that caller, not verified by Minecraft. No game UUID or public player speech
is fabricated. The body retains original time separately from receipt time,
original text unchanged, and caller/actor/audience separately. New sources must
be within the existing ten-minute source lifetime, not future or Stop-revoked.
The envelope is metadata only: it grants no new work, renewal, or effect replay.

A successful response is `{queued:true,request_id,source_request_id,received_at,
duplicate:false}`. `request_id` is the generated original game queue UUID;
`source_request_id` is the submitted UUID. Persist both and the exact envelope.
Repeating the identical caller/source request and payload returns the same queue
UUID with `duplicate:true`, including after restart or a lost HTTP acknowledgment.
It does not requeue or freshen an old input. Changed payload with the same source
request ID is rejected. A new revision needs a new explicit source UUID; it does
not cancel/replace an existing active input. Queue rejection persists no receipt.

For read-only outcomes, POST:

```json
{
  "version": 1,
  "requests": [{
    "request_id": "the-original-generated-queue-uuid",
    "source": "the complete exact original source OBJECT shown above"
  }]
}
```

Replace the explanatory `source` string with the original object. Up to 16
unique queue IDs are accepted. The query matches the credential-derived caller,
queue UUID, source UUID, call, intent, revision, actor, audience and original
time. Unknown and non-matching identities receive the same content-free unknown
outcome. Querying an old retained source is allowed; it cannot requeue it.

Responses contain version, fresh `observed_at`, and outcomes distinguishing
queued/admitted/terminal/interrupted. Original source attribution accompanies
only authorized matches. `response_association` says `single_source`,
`shared_turn` or `not_established`; co-admission is not an exclusive answer.
Other inputs' IDs are omitted. Attributable public speech remains public and
immutable. Minecraft whispers and unrelated private control remain withheld.
There is no new private-response tool or automatic forwarding of private speech.
`completion:not_established` remains explicit: prompt settlement or a task
transition is not proof of completed physical work.

Keep the durable source receipt ledger during updates, Stop and recovery. Do
not prune it into a replay opportunity. Original task IDs, counts, unknown
receipts, provider constraints and world-effect guards remain independent.
