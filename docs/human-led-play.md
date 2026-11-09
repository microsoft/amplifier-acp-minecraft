# Human-led play

`human_engagement.enabled: true` is an explicit installation policy. It removes
this connector's hourly human-reply quota, autonomous planner pacing and legacy
24-action turn cap. Host
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

## Task-optional activity

Owners may explicitly set both `human_engagement.enabled: true` and
`human_engagement.task_optional: true`. This permits ordinary survival activity
within the installation's purpose and current human instructions: movement,
inspection, gathering and helping do not need a task record or an acceptance call.
Code updates alone do not enable this policy. Existing chat-only installations
remain chat-only unless their owner opts in.

A blocked design does not prohibit unrelated permitted help. Existing task IDs,
explicit limits, consumed counts and closed commissions stay intact. Task-bound
continuations still enforce those limits; ordinary activity must not be used to
resume an expired or stopped commission. Tasks remain useful optional records
for sustained responsibilities and explicit human constraints.

Ordinary effects use the existing controller lease and action receipts with
`task_id: null`; no hidden task is created. `work_report` records ordinary progress:
`running` schedules useful follow-through, while `waiting`, `blocked` or `review`
ends that continuation. It is not permission to act. New relevant input can lead
to other permitted activity. Do not poll dependencies or invent busywork.

Stop persists independently of task records. Neither a restart, ambient/peer
input nor toggling policy clears it. `resume_activity` requires an original,
fresh, current transport-attributed human instruction explicitly resuming activity.
It does not reopen a task or clear uncertain effects. Unsettled/interrupted
ordinary effects remain held for inspection; never replay them.

### Reviewing a proven no-effect activity failure

An unsupported `place.facing` argument is rejected before action admission, so
it does not create an uncertain world-effect receipt. Repeater/comparator
horizontal facing is supported and verified against the server's block properties;
placement or orientation mismatches still require inspection and are not retried.

For a historical failure, the authenticated owner control
`POST /activity/review-no-effect` accepts `generation` (from `/conversation`),
`expected_turn_sha256` (SHA-256 of JavaScript `JSON.stringify(last_turn)`),
`action_id`, and a concrete evidence `reason`. This is not a planner tool. Review
requires an idle, non-interrupted ordinary-activity turn with exactly one uncertain
action and all other actions successful. Inspect the exact failed call and source
before asserting no effects. Stale reviews, pending operations and interrupted
turns refuse. The original uncertain receipt is retained with the dated no-effect
review; tasks, Stop, prior input and accounting are unchanged. Read state after a
lost response; do not repeat a failed game action or infer renewed work authority.

### Route destination facts

`plan_route` reports loaded feet/head/support geometry at its target. An exact
full-block obstruction returns `target_obstructed` without searching or moving.
Target Y is feet height, not floor height. A nonzero horizontal range still allows
nearby endpoints; partial and unloaded shapes are reported without inventing
clearance. The agent chooses any alternative and movement rechecks the world.

## Public speech

`chat` and `tell` submit explicit public utterances (or the current private reply
for a whisper). Once either is attempted, the final assistant answer is not also
broadcast. Additional public statements use another explicit speech call. A
failed attempt remains failed/unknown, not delivered. Direct turns with no speech
tool still support a final-only answer; peer/activity turns use explicit tools.

A completed utterance may contain up to 4,000 characters. The adapter splits it
at sentence/word boundaries into paced, addressed packets within the Java limit.
Per-packet submission receipts preserve order. Stop/new conversation interrupts
unsent packets; a partial or unknown submission is not automatically replayed.
Submission is not proof every player received it.

## Legacy task-required mode: human replies within an existing assignment

With human-led play enabled, a fresh transport-attributed human reply can use
world tools already authorized by the same running or waiting assignment.
Merely replying consumes no work allowance. The first work tool durably reserves
one existing task turn, binds the ordinary renewable action lease and follows
normal effect settlement/recovery. This avoids promising movement while the
reply tool policy forbids it.

The task ID, bounds, consumed count and authority revision must still match the
assignment observed at reply admission. Stop, expiry, exhaustion and unresolved
interruption remain binding. Peer proposals and ambient activity stay effect-free;
new acceptance or amendment still needs a subsequent work turn. A reply grants
no new scope, allowance or authority. Private replies retain their audience even
if they use existing work authority. The controller records promoted work in
`calls.json` as well as the original human-reply attempt.

## Continuation and interruption

An optional peer, activity or attention delivery uses a separate conversation turn,
including plain ACP peer delivery. Its rejection
or transport failure does not consume a construction turn or interrupt the
existing assignment. Unavailable optional delivery stays queued until its own
expiry; it cannot prevent separately authorized work from continuing. Tickets
are never stripped or retried as ordinary input.

With `automatic_recovery` enabled, the controller can inspect recovery evidence
while world effects remain closed. The existing helper and receipt checks must
approve before the same assignment resumes. Pending or uncertain effects,
explicit Stop, exhausted human limits, missing helper support and exhausted
recovery attempts still prevent automatic resumption. Recovery retains task
identity, source authority and spent counts; it does not extend work or replay
an earlier action. The adapter never treats an arbitrary ACP error code as proof
that no input was forwarded.

## Continuous action plans

`action_sequence` accepts an agent-selected ordered list of up to sixteen
ordinary `move`, `place`, `build`, `craft`, `dig`, `set_open` or `till` operations.
Every step uses the existing schema, authority, geometry and result checks.
No arbitrary code executes. The planner can combine compatible steps without
waiting for a new model response between each. The full plan is validated before
its first effect. Any configured current-turn action budget still applies; human-led mode reports
no connector action-count cap, while actual assignment limits remain binding.

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

While an operation is running, `plan_route(mode="walk_only")` performs a bounded
read-only search without touching the live pathfinder. Optional `start` specifies
whole-block coordinates for a hypothetical future stance. Results include the
actual current feet, planned origin and `hypothetical_start`; they never imply
arrival. Normal pathfinder planning still waits for movement to settle. Queued
movement always plans again from its actual position before executing.

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

`human_activity` reports loaded server-attributed movement and human arm-swing
animations, excluding configured agent names. An arm swing is only evidence of an
interaction attempt; its target and result are unknown. First observed presence
and stationary/AFK presence are not activity. Activity expires after two minutes
without another observed action. These are observed
facts for planners; this revision does not synthesize human commands or enable
idle model polling from movement. Movement-driven social engagement, completion-bound assignments and independently
accepted delegation require the explicit installation policies described below. None are implied by a cosmetic change or transport
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
admission remain separate outcomes. Movement and server-attributed arm-swing interactions are observed; an interaction
attempt does not establish its target or success.

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

Acceptance retains both original receipts, creates one independent task within the recipient’s configured bound policy,
and commits consumed source IDs with it. Retries/restarts return that outcome;
they cannot create another allowance. Any finite helper deadline is anchored to the
original human source time, never refreshed by a later peer handoff. Existing
work, unresolved effects, Stop, installation ceilings and source expiry remain
enforced. Original public sources for a new assignment must still be within the
ten-minute intake window. Existing active assignments can incorporate proposals
under retained human instructions from that assignment without resetting spent
work or limits; see [task intake](human-task-intake.md#continuing-an-existing-assignment).
Existing expired work is archived unchanged if new work is accepted.

Peer-proposal replies retain ambient attention/routing gates and their own local
reply bound (four per hour by default, configurable from one to twelve through
`human_task_intake.delegation.reply_turns_per_hour`). They never take the
unmetered human-message lane. Ordinary ACP engines can use the same MCP tools;
no native receipt or invented host delegation API is assumed. World effects
remain denied in the acceptance reply and require a later valid work turn.

## Completion-bound assignments

See [completion-bound tasks](completion-bound-tasks.md) for opt-in defaults,
local helper capability discovery and legacy compatibility.

Activity coalescing preserves one exact pending observation per actor for its
original two-minute lifetime. Continued walking cannot replace the source while
host judgment is in flight. Expired observations still reject late results; the
next actual action supplies a fresh source. This neither manufactures chat nor
bypasses the host's social judgment, ambient quotas, explicit Stop or task scope.

Peer conversation and work authorization are separate. With human-led play and
`agent_dialogue` enabled, public peer inputs remain independently pending while
the inbox is full, and host engagement is not overridden by another local
four-replies-per-hour or recent-human window. Host attention/provider limits and
source expiry still apply; plain ACP retains ordinary prompt fallback. An
attributed, admitted peer report can receive an effect-free reply even after the
original human intake source expires. Accepting helper work still requires the
original human authorization; conversation never grants or renews it. Legacy
installations retain their configured peer limits.

`observe` includes server roster join/leave facts and the current online roster.
The initial roster on connection is not reported as a burst of new joins. These
facts do not synthesize chat, automatically greet players or authorize work.
Crop watches can use `environment:crops` with a path such as
`/by_position/-2,63,1/properties/age`; absence means unobserved, not harvested or
ripe. The legacy `blocks` array remains available. Container obstruction errors
include the actual raycast blocker and eye/target geometry, without moving or
choosing a route for the agent. Exactly duplicated public text is shown once in
the recent planner view; full owner evidence remains available.
