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

`work_report(running)` continues useful work. `waiting`, `blocked` and `review`
end that continuation. Finishing one substep is not inherently a reason to wait
for another human instruction. The model chooses its approach and report; this
change does not synthesize tasks, ignore authored waits or replay unknown work.

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
