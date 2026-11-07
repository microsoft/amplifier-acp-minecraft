# Completion-bound tasks and independently bounded operations

An installation may set `human_task_intake.default_bound_mode` to
`"completion_bound"`. The default when omitted is `"finite"`, preserving existing
installations. This policy affects only newly accepted human assignments (or
separately accepted, explicitly authorized helper work). It neither converts old
tasks nor revives expired work. Intake still requires original attributed human
source evidence, durable acceptance and a later work turn; acceptance itself has
no world effects.

Before completion-bound intake, the body discovers the configured local
`decision_attention.command` with `helper-capabilities`, without a home, provider,
session or model call. It requires schema version 1 and **both** helpers:

- `watch`: version 2, command `watch-v2`, bound kinds `finite` and
  `no_configured_bound`, watch TTL minimum 30 / maximum 1800 seconds.
- `continuation`: version 2, command `continuation-v2`, the same two bound kinds.

This is not inferred from Instance version, ACP engine family, attention support,
or the Runtime version string. Failed/missing discovery blocks new completion-bound
acceptance and is reported in `task_capabilities`; it does not substitute a large
number or silently accept finite work instead. Discovery is cached against the
local binary's filesystem identity and rechecked when task tools are used. A
changed binary cannot retain the old capability result. Existing finite tasks
continue using the legacy commands and exact numeric projection. Ordinary ACP
engines can use the same domain tools with a separately configured local helper.

New completion-bound records have `bounds.version: 1`, `bounds.deadline_ms` and
`bounds.max_turns`. Each is explicitly `{ "kind": "finite", "value": N }` or
`{ "kind": "no_configured_bound" }`. Finite values have matching legacy numeric
fields for inspection; unbounded dimensions omit those fields. Missing/null,
unknown tags, contradictory duplicate fields and unknown consumed counts never
grant unlimited work. Summaries report null remaining capacity only alongside
explicit tagged bounds; invalid records are labeled unknown.

For the opted-in default, omitted tool limits mean no configured assignment bound.
Explicit human `max_turns` or `seconds` remain finite and must fit the installation's
existing numeric ceilings. Null is not a valid tool limit. Finite helper deadlines
remain anchored to the original human request time. Both bound dimensions are
projected into v2 helpers; original task identity, watch store, event cursors and
call accounting remain unchanged. A watch always has its own finite TTL and
cannot be revived by removing an assignment deadline.

Human amendments may impose a finite limit on an unbounded dimension. Reductions
below consumed work, including zero, or a past deadline stop further work while
retaining spent counts and all receipt/recovery evidence. Duplicate/lost-reply
amendments return the recorded outcome after restart. This revision does not add
a tool to remove a previously explicit finite limit. Stop, unresolved effects,
recovery ceilings, completed/reviewed/blocked state and explicit human limits
remain independent of configured task duration.

Action authority still uses the renewable 240-second controller lease. A
completion-bound assignment permits further lease renewal only for its same
running task/turn/revision; it does not make a lease infinite. Each operation,
watch observation, provider connection and cancellation settlement has its own
bounded lifecycle. No second controlling prompt, replay, automatic task renewal
or periodic model polling is introduced.
