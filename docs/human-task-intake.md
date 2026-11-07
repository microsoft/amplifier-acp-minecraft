# Human task intake

This opt-in Minecraft policy lets any server-attributed human participant request
bounded work or amend its limits. It does not use an owner-only requester list,
a native runtime extension, or the Instance responsibility ledger as execution
authority. Social engage/hold remains Instance-owned where advertised; ordinary
ACP fallback still works.

Set `human_task_intake.enabled` explicitly after reviewing the installation.
`task_max_turns` and `task_max_seconds` remain the defaults. The policy's
`max_turns` and `max_seconds` are installation ceilings; if omitted, they equal
the defaults. Increasing these ceilings is an installation policy change, not
something a peer or model can grant itself. The maximum supported configuration
is 10,000 cumulative turns and seven days; this is a validation bound, not a
recommended allowance. The existing 30 work-turn/hour pacing and provider caps
are independent and unchanged.

`task_capabilities` exposes effective mode, defaults, ceilings, current revision,
allowed task transitions, current consumed/remaining work, hourly pacing and
distinct blocked reasons. Provider remaining capacity is explicitly unknown here;
the connected host/provider still enforces its own limits. Persistent `chat_only`
configuration is different from a temporary human reply reserve. Repeating a
message or waiting for capacity does not clear a disabled intake policy.

When intake is enabled, `incoming_chat_only` still does not revive any existing
assignment. Only a new task with this policy's recorded human authority can run.
With `incoming_chat_only: true`, disabling intake closes that path again.
Legacy work mode (`incoming_chat_only: false`) retains its existing behavior. Stop still cancels current action
leases and revokes unused sources older than the stop.

This implements a bounded local subset of the shared
[task-admission contract](https://github.com/microsoft/amplifier-constellation/blob/6c122d8c14f52f103484536d7005ac37163e17ef/contracts/task-admission.v1-candidate.md).
It adds no ACP fields or host API. Delegation remains unavailable as described below.

## Acceptance and amendments

The human reply reserve may invoke `task_accept` and `task_amend` when the policy
is enabled. These are metadata transitions: no world effect or action lease is
opened by either call. A successful acceptance records a task with zero consumed
work turns; a subsequent ordinary controller turn must pass normal capacity and
authority checks. Acceptance is not execution, completion or peer acceptance.

The reasoning agent identifies an actual assignment from the human's language;
a greeting alone never creates a task. The body enforces source provenance,
current reply binding, freshness, ceilings and durable deduplication. The source
must be public, routed human chat from the last ten minutes, bound to the current
reply. It must have server player UUID attribution matched to the player registry
and the parsed username. Configured peer names are classified as agents without
case sensitivity. Parsed system messages or model-supplied speaker fields cannot
create transport proof. Attribution means the configured Minecraft server vouched
for the player UUID; it is not a claim that every bridged client has a verified
Mojang chat signature. Missing attribution fails closed for new task authority,
while normal conversation may still respond. Durable source receipts explicitly
include the original actor, time, public audience and a stable source revision.
That revision hashes the source identity/content facts, not surrounding routing
context; the full original evidence has a separate hash.

`task_amend` names the current task and expected authority revision. `max_turns`
is the cumulative cap, never a fresh balance; `deadline` is an absolute Unix
millisecond timestamp. Consumed turns and original source remain intact. A lower
cap may be below consumed work, including zero: that exhausted allowance closes
further work rather than erasing consumption or rejecting the reduction. A past
positive deadline similarly closes further work. Exhaustion wins even if the
request also supplies `resume`. Amendments execute only in the effect-free human
reply turn, after prior game operations settle; they cannot open a lease. An
explicit human-requested `resume` amendment can continue an expired task admitted
under this policy, within ceilings. Expiry cannot erase an unresolved interruption. Stopped or interrupted/uncertain tasks still
require their existing review path. A mode change alone never resumes them.
Duplicate calls return the original acceptance receipt plus current status and do
not change limits, consume another turn or enqueue work. Different arguments using
an already consumed source are rejected. Persist failures do not leave new authority
live in memory. No failed/unknown input is automatically replayed.

## Retained requests from before the feature

Keep the exact original request as evidence instead of demanding repetition only
because the old installation could not accept it. An authenticated operator may
review an unused retained public human event at an idle boundary using
`POST /task-source/review`: `request_id`, `expected_source_hash`, `reason`, and an
optional `valid_for_seconds` (default 600, maximum 3600). The hash uses the exported
`digest` helper from `task-intake.cjs` over the exact saved event. This endpoint is
not an MCP tool. It archives the original event and labels evidence as
`authenticated_operator_review`; it never invents missing transport attribution.
A source can be reviewed once. Review does not start a model turn or assignment,
renew a task, enqueue the old message, acknowledge an unknown receipt, or grant
world effects. The next genuine human conversation may refer to this retained
source within its bounded review window. Stop invalidates older retained sources.

## Delegation and speech limits

Independent helper acceptance is available only through its explicit installation
policy and original human provenance, as described in
[human-led play](human-led-play.md#independently-accepted-helper-work). Instance
work export/import remains responsibility evidence, not a world execution grant.

Newly accepted work may use explicit completion-bound defaults after local helper
capability discovery. See [completion-bound tasks](completion-bound-tasks.md).
Existing finite tasks and their consumed counts are never converted by a mode change.

Final, settled public replies prefer complete sentences and are packetized at
sentence boundaries where they fit, falling back to word boundaries and then
bounded Unicode-safe fragments. This is platform presentation only: punctuation,
empty envelopes and network chunks are not ACP completion signals. Published
packets are never rewritten; freshness checks stop an unsent tail after changed
context, and ambiguous delivery is not replayed.
