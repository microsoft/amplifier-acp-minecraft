# Human-led play

`human_engagement.enabled: true` is an explicit installation policy. It removes
this connector's hourly human-reply quota and autonomous planner pacing. Host
and provider limits still apply. Source IDs remain durably consumed, audiences
remain separate, and possibly accepted input is never replayed after a lost
reply. Existing assignment deadlines, consumed counts, explicit stops and
unresolved effects are preserved; changing this setting is not a task renewal.

Server-attributed, explicitly addressed human messages (including group,
whisper and current conversational followup) enter the human input queue without
waiting for an optional social-attention decision. Other public conversation
continues through the negotiated Instance attention interface or plain ACP
fallback. This is not a claim that every unaddressed human sentence is intended
for every agent. The setting removes the three-second artificial continuation
delay as well. All actual planner calls remain measured.

## Continuous action plans

`action_sequence` accepts an agent-selected ordered list of up to sixteen
ordinary `move`, `place`, `build`, `craft`, `dig`, `set_open` or `till` operations.
Every step uses the existing schema, authority, geometry and result checks.
No arbitrary code executes. The planner can combine compatible steps without
waiting for a new model response between each. The full plan is validated before
its first effect. The normal current-turn action budget still applies.

A new human input, changed authority, Stop, explicit `cancel_sequence`, failed
step or partial/unconfirmed result prevents further steps. Cancellation waits
for the current operation to settle; it does not falsely claim an in-flight
operation never happened. Normal read-only observations remain available while
a plan runs. A second effectful plan cannot run concurrently.

`start_sequence` starts the same guarded plan asynchronously and returns its
operation ID with `accepted: true`, `completed: false`. The existing controlling
prompt can continue reasoning, observe current facts, and use chat/tell while
physical steps run. Speech retains its audience, conversation revision and
settled action receipts without taking ownership of the physical action.
There is still only one controlling ACP prompt per saved session.

`sequence_status` returns actual retained results and can wait up to 30 seconds
for settlement. Acceptance is not completion. Inspect those results before
reporting success or starting another plan. If the planner ends early, the
controller waits for the operation under the same renewable action lease and
assignment limits; it withholds a final claim made without those results.
Stop, a failed prompt or closed authority cancels unstarted steps. An unresolved
physical effect remains uncertain and is never replayed or called complete.

Use a unique `plan_id`. The body stores the plan before execution and records
step outcomes. Repeating that ID reads its retained receipt without replaying
work; different contents under an existing ID are rejected. After a crash, a
running receipt is interrupted, not automatically resumed. Consumed identifiers
survive detailed-receipt eviction. Owner-local plan receipts do not export raw
arguments or results to the shared conversation context.

## Progress and activity evidence

When a successful planner terminal omits `work_report`, one subsequent
reassessment is allowed only if every recorded effect succeeded. The body saves
an explicit missing-report checkpoint, not a completion claim. A repeated
missing report, no action evidence, an uncertain effect or an error does not
start an endless continuation loop. Stops and exhausted assignments stay closed.

`human_activity` reports loaded server-attributed movement, excluding configured
agent names. First observed presence and stationary/AFK presence are not movement.
Activity expires after two minutes without further movement. These are observed
facts for planners; this revision does not synthesize human commands or enable
idle model polling from movement. Movement-driven social engagement, default
completion-bound assignments and independently accepted delegation require their
own policy integration. None are implied by a cosmetic change or transport
health check.

Public participation inputs have independent durable outcomes. Each evaluation
binds one source ID and its original time; later messages do not consume it or
replace its bounded context snapshot. A hold consumes only that source. Pending
source evidence survives observation-journal rollover within the existing
10-minute input lifetime. Expired/unavailable sources receive an explicit local
outcome, and accepted sources cannot be replayed after a lost delivery reply.
Stop clears pending sources and their snapshots. This does not renew task limits
or make unknown participants human.

`human_engagement.activity_scope: "conversation_only"` explicitly permits an
ambient greeting/help opportunity based on observed movement. It does not grant
movement, construction, task intake/amendment, delegation or renewal. Stop disables
activity opportunities. Without this installation setting, collection stays passive.

Activity is coalesced at ten-second intervals per observed human, expires after
two minutes, and retains its original source ID/revision/time across delivery and
restart. Stationary presence and configured agents do not produce opportunities.
The adapter requires the advertised Instance attention parent and `activity` v1
subcapability before sending `context.activities`. Older/disabled hosts keep
observations in ordinary tool context; activity is never turned into fabricated
chat or a second local social-model call. Host engagement and actual prompt
admission remain separate outcomes. The initial implementation observes movement;
interaction event capture is not yet implemented.

## Independently accepted helper work

`human_task_intake.delegation.enabled: true` enables `task_accept_help` for a
recipient's effect-free peer-proposal reply. It does not grant a lead control of
another agent. Both the original human request and the fresh peer request must
exist in the recipient's own public game transcript with server UUID attribution.
A peer's copied quotation, supplied actor name or responsibility record is not
accepted as the original source.

The recipient interprets the original human instruction and must supply an exact
quote of explicit helper authorization and `budget_scope: independent_per_agent`.
The initial implementation supports independently authorized per-agent limits,
not allocation of a shared aggregate budget or further delegation. Ambiguous
scope needs clarification. Mechanical source validation does not prove the
model interpreted the human's meaning correctly.

Acceptance retains both original receipts, creates one independent bounded task,
and commits consumed source IDs with it. Retries/restarts return that outcome;
they cannot create another allowance. The helper deadline is anchored to the
original human source time, never refreshed by a later peer handoff. Existing
work, unresolved effects, Stop, installation ceilings and source expiry remain
enforced. Original public sources must still be within the ten-minute intake
window. Existing expired work is archived unchanged if new work is accepted.

Peer-proposal replies retain ambient attention/routing gates and their own local
reply bound (four per hour by default, configurable from one to twelve through
`human_task_intake.delegation.reply_turns_per_hour`). They never take the
unmetered human-message lane. Ordinary ACP engines can use the same MCP tools;
no native receipt or invented host delegation API is assumed. World effects
remain denied in the acceptance reply and require a later valid work turn.
