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
a plan runs. A second effectful plan cannot run concurrently. Whether an engine
can reason during a pending tool call depends on its actual ACP implementation;
this tool does not invent a parallel-prompt capability.

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
