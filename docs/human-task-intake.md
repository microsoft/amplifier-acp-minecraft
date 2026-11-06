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
allowed task transitions and distinct blocked reasons. Persistent `chat_only`
configuration is different from a temporary human reply reserve. Repeating a
message or waiting for capacity does not clear a disabled intake policy.

When intake is enabled, `incoming_chat_only` still does not revive any existing
assignment. Only a new task with this policy's recorded human authority can run.
With `incoming_chat_only: true`, disabling intake closes that path again.
Legacy work mode (`incoming_chat_only: false`) retains its existing behavior. Stop still cancels current action
leases and revokes unused sources older than the stop.

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
while normal conversation may still respond.

`task_amend` names the current task and expected authority revision. `max_turns`
is the cumulative cap, never a fresh balance; `deadline` is an absolute Unix
millisecond timestamp. Consumed turns and original source remain intact. An
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

Execution delegation is explicitly unavailable in this revision. Peer requests
and Instance work export/import cannot mint human world authority. A future
lead/helper path must preserve the original human delegation authorization and
independent recipient acceptance; it must not copy a ledger record into an
execution grant. The agent must state the current limitation rather than promise
that recruiting others has already started work.

Final, settled public replies prefer complete sentences and are packetized at
sentence boundaries where they fit, falling back to word boundaries and then
bounded Unicode-safe fragments. This is platform presentation only: punctuation,
empty envelopes and network chunks are not ACP completion signals. Published
packets are never rewritten; freshness checks stop an unsent tail after changed
context, and ambiguous delivery is not replayed.
