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
revisions, inventory selection and partial results. Tool responses retain lease
and capacity facts without appending the same behavioral warning on every call.
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
