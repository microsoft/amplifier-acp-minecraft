# Installation-owned Minecraft updates (implementation in progress)

This document describes an unfinished provider/participant implementation. It
does not enroll an installation, enable a schedule, or authorize world work.
The generic installation updater owns scheduling and release selection. The
Minecraft installation owns its source, dependencies, helper and game boundary.

## Components

* `minecraft`: one reviewed exact source revision, its npm lock and isolated
  dependencies, and an installation-local Python environment. Verify the official
  ACP SDK's `direct_url.json` immutable upstream commit, not its version alone.
  Build and validate before closing game admission. Source rollback must never
  restore old workshop, session, input, authority or accounting files.
* `task-helpers`: a separately selected published executable, digest checked
  before execution. Discover support with the static `helper-capabilities`
  command. Installation of this pure helper must not select a native engine,
  change credentials, evaluate a watch, or invoke a model. Existing watch stores,
  cursors, TTLs and accounting remain unchanged.
* `minecraft` lifecycle participant: applies whenever an enrolled instance,
  runtime, external engine, container image, Minecraft or helper component changes,
  even if Minecraft itself has no candidate. Scope uses explicit registered
  component IDs; no name guessing or global fleet service discovery.

Use command provider protocol 2 (`status`, `plan`, `apply`, `rollback`, `verify`)
with the worker's immutable saved plan. Do not follow an unchecked default branch
or downgrade implicitly. Stable and tested-development selection are explicit
installation choices. A missing stable artifact is not permission to substitute
development source. The provider must bind source, dependency provenance,
artifact hashes, platform and enrolled destination to the plan.

## Participant protocol and transaction boundaries

Target lifecycle protocol 1 supplied by the generic updater: fixed enrolled
`prepare`, `verify`, `restore` commands; immutable `CONSTELLATION_UPDATE_PLAN`
context; `CONSTELLATION_UPDATE_OUTCOME` of unchanged/applied/rolled_back.
Context carries the transaction ID, apply/rollback operation, changed component
IDs and restart scope. Protocol-2 providers also receive
`CONSTELLATION_UPDATE_TRANSACTION` to find the same participant receipt.

1. Acquire an installation-local exclusive lock. Capture original active,
   enabled, mask, unit-definition and process states in a private durable receipt
   **before** any service/admission mutation. Never touch unrelated services.
2. Close only new Minecraft admission with a durable transaction-owned body
   gate. A read-only idle check followed by stopping a controller is insufficient:
   another turn can enter between those operations. In-flight work and its
   existing lease may settle; do not cancel, finish or renew a task to obtain idle.
   Return `ready:false,reason:busy` promptly while unsettled. The command budget
   is 30 seconds; repeated prepare calls use the same receipt and gate.
3. At a genuinely settled boundary, stop/mask only captured controller units and
   verify no race. Record a stable baseline of every authority/history field,
   saved session/binding/accounting/unknown-receipt file, inventory and position.
   Shared-only updates retain body processes. A source/dependency update may
   separately stop/restart only its captured body after this boundary.
4. Verify candidate or restored previous source/dependency/helper and continuity.
   Only narrowly plan-authorized code/dependency pointers may differ. New human
   observations must be retained; never overwrite a full workshop snapshot to
   make a hash match. Changed authority or unsettled/unknown current effects
   require reconciliation rather than automatic rollback of state.
5. The worker persists successful verification before any participant restores.
   Restore only transaction-owned admission/mask changes and previously active
   services, in body-then-controller order. Preserve pre-existing stopped/masked
   state. External mask, enablement or unit changes prevent automatic restoration.
6. After a crash or lost reply, inspect the durable stage and actual state.
   Repeated prepare/verify/restore must not recapture a changed baseline or replay
   effects. An uncertain source cutover needs verification/rollback of code only;
   an already verified transaction resumes restoration, never a new rollback
   after a listener may have resumed work.

## Current implementation and remaining work

`installation_guard.py` provides strict observation/continuity comparisons,
original-state restoration intentions, exclusive locks and durable receipts.
Tests cover busy/unknown boundaries, expired tasks and historical unknown inputs,
new authority/accounting fields, retained incoming events, process/world drift,
pre-existing and external pauses, and lost replies.

Not implemented yet: the atomic body/controller admission gate, actual lifecycle
CLI driver and enrollment, frozen source/dependency staging and provider actions,
helper provider, actual worker-boundary fixtures and Inspector integration. Do
not treat these primitives as a complete or deployed automatic updater.

The first installation of admission support itself requires a newly coordinated
idle cutover; it cannot rely on a gate absent from the installed version. Subsequent
scheduled updates use the installation-owned participant without requesting
operator permission for each ordinary idle update. None of this renews expired
assignments, replays unknown inputs, changes engine families, or enables a
previously disabled work policy.
