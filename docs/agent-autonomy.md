# Minecraft autonomy and truthful capabilities

An installation that permits task-optional play does not require a task ticket
for ordinary survival work. Its capabilities describe effective permission:
`configured_chat_only` is true only when the installation permits neither task
intake nor ordinary activity; `conversation_only` describes whether the current
reply can perform work. The original reply admission and input accounting retain
their stored values. `/status` keeps the controller's internal admission flags;
model-facing observations use effective capabilities.

A legacy `incoming_chat_only: true` setting can coexist with enabled human task
intake and task-optional play. Presenting that setting as a blanket prohibition
was misleading: a player could report being chat-only while its tools already
permitted movement. Stop and unresolved effects remain actual restrictions and
are reported as such, without modifying historical task or action receipts.

The Minecraft prompt supplies world context, speech routing and continuation
semantics. It does not prescribe a universal inspect/map/route/meeting checklist,
ban other authorized tools, or require renewed permission for routine choices
within ongoing work. Tool descriptions retain mechanics such as reach, required
revisions, inventory selection and partial results. Tool responses retain operation bounds
and capacity facts without appending the same behavioral warning on every call.
Controller lease IDs/expiry stay on the authenticated control interface, where
renewal belongs, rather than appearing as a model reasoning deadline.
A verified result may be reported as verified; `review` is a continuation state,
not a prohibition on describing completion.

`work_report(running)` continues useful ordinary work. A settled `waiting` or
`blocked` report, or a normal finish without a report, permits fresh planning
after the existing five-minute reconsideration interval. A missing material or
stalled method is not a requirement to wait for a human or supplier. The model
can reconsider methods and other permitted work. This does not claim a dependency
resolved, change a formal task or its bounds, or replay an earlier input/action.
An explicit `review`, Stop, interrupted/unknown effects and current installation
or provider limits still prevent continuation. Reports remain truthful records;
the controller does not invent a report, completion, or new task.

## Placement across components

Identity, general collaboration and tool access belong to the agent installation
and its shared engine interface. Minecraft should not override them with another
generic personality or a blanket ban on other experiences. World ownership,
survival mechanics, public/private game speech and Minecraft continuation state
belong here. No new shared scheduler, permission service or runtime-specific
prompt mechanism is introduced to correct contradictory Minecraft descriptions.

Source tests establish consistent permission reporting and preserved Stop,
unknown-effect and task accounting behavior. They do not establish that a model
will complete a build or choose better plans; that requires observing actual work.

## Concurrent speech and initial refusals

An unrelated chat update is context, not cancellation of a composed utterance.
Explicit speech keeps its original audience and ordered packet receipts while
new context arrives. Stop, turn termination and unknown transport still halt
submission; a repeated partial utterance is refused rather than resent. Physical
handoffs retain their separate conversation and inventory checks.

Initial handoff target/range/spacing checks run before reserving an effect. A
refusal at that point leaves the player free to choose a different approach.
After preparation or dispatch, uncertain effects remain uncertain.

The existing owner-only settled-action review can recognize an exact historical
initial range refusal, or an old conversation-change speech cancellation with a
fully receipted submitted prefix and explicitly cancelled suffix. It preserves
original statuses, packets, task/input accounting and Stop. It permits future
independent work, never resends speech or resumes the old continuation. Any
submitting/unknown packet, missing receipt or transport failure remains held.


## Settled failures and usable capabilities

A completed operation can fail its goal without leaving execution unknown.
Internal settlement evidence follows the exact error through composed tools;
for example, a settled approach failure is still settled when it occurred inside
placement. Read-complete storage validation before any transfer click retains
its window preparation but does not freeze all future work. Error text alone,
unacknowledged clicks, transport loss and timeouts are never settlement proof.
Existing owner reviews preserve original historical receipts and permit only
fresh work, not continuation/replay of a reviewed action.

A stale follow target is an observation to reconsider, not an uncertain movement.
Initial identity checks happen before action admission and again before setting
the movement goal. A known refusal at either point permits a fresh choice; no
replacement target is selected automatically. Once movement starts, target loss,
timeouts and unclassified failures still retain uncertainty. The authenticated
owner review can recognize an exact older initial identity refusal, preserving
its original receipt and permitting only fresh work rather than replay.

A build is a sequence of placements, not an all-or-nothing transaction. If a
later target is refused before its placement preparation starts, the verified
prefix remains completed work and the suffix remains unattempted. The partial
result permits a fresh plan without a global unresolved-effects hold. Unverified
placements, lost acknowledgments and post-preparation races remain distinct;
the connector does not clear obstacles or retry the batch automatically.

Observations include the exact retained blocking receipts even when they have
aged out of recent events. `available_tools` describes the installed primitives;
`pathfinder_can_break_blocks` describes automatic pathfinding only. Separate
`dig` and `gather` remain available under normal work authority. Choose methods
from current tools and facts; a missing supply or failed method is not a reason
to wait for the human when another permitted plan is useful.

`equip` selects an inventory item, `consume` eats one registered food, and
`attack` strikes one explicitly selected non-player mob without pursuit or
repetition. Preserve breeding stock/player animals; named/owned and baby targets
are refused. Server damage/death observation is not proof of collected food or
exclusive kill credit. Inspect inventory and dropped items afterward. These
primitives use the existing tool identity, permission, action lease and budget
checks; they do not grant general commands or bypass Stop. Other absent
capabilities should be reported precisely, not invented or worked around through
unapproved tools. General initiative belongs in agent guidance; Minecraft
geometry, tool outcomes and world protections remain in this connector.
