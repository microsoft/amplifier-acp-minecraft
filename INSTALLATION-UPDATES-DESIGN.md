# Installation-owned Minecraft updates

The included provider and participant are opt-in installation tooling. Merely
updating this repository does not enroll an installation, enable a schedule, or authorize world work.
The generic installation updater owns scheduling and release selection. The
Minecraft installation owns its source, dependencies, helper and game boundary.
This lifecycle driver currently supports Linux with systemd user services. The
game adapter remains portable; do not enroll this optional driver on another OS.

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
3. At a genuinely settled boundary, stop only captured controller units and
   verify no race. Record a stable baseline of every authority/history field,
   saved session/binding/accounting/unknown-receipt file, inventory and position.
   Shared-only updates retain body processes. A source/dependency update may
   separately stop/restart only its captured body after this boundary.
4. Verify candidate or restored previous source/dependency/helper and continuity.
   Only narrowly plan-authorized code/dependency pointers may differ. New human
   observations must be retained; never overwrite a full workshop snapshot to
   make a hash match. Changed authority or unsettled/unknown current effects
   require reconciliation rather than automatic rollback of state.
   Instance/runtime/engine/container/source changes also initialize and load the
   original saved game session through the installed official-SDK client while
   admission stays closed. Binding mismatch, unsupported load, missing backend
   session or bounded operation timeout fails verification; never create a
   replacement or prompt to prime persistence. An installation with no saved
   session performs initialize only and verifies the local session remains absent;
   it never opens a new session to prime persistence. A helper-only change does
   not open ACP. Recheck continuity after loading, including on engine rollback.
5. The worker persists successful verification before any participant restores.
   Restore only transaction-owned admission/mask changes and previously active
   services, in body-then-controller order. Preserve pre-existing stopped/masked
   state. External mask, enablement or unit changes prevent automatic restoration.
6. After a crash or lost reply, inspect the durable stage and actual state.
   Repeated prepare/verify/restore must not recapture a changed baseline or replay
   effects. An uncertain source cutover needs verification/rollback of code only;
   an already verified transaction resumes restoration, never a new rollback
   after a listener may have resumed work.

## Implementation and enrollment

`installation_guard.py` provides strict observation/continuity comparisons,
original-state restoration intentions, exclusive locks and durable receipts.
Tests cover busy/unknown boundaries, expired tasks and historical unknown inputs,
new authority/accounting fields, retained incoming events, process/world drift,
pre-existing and external pauses, and lost replies.

`installation_participant.py` implements lifecycle v1. The body synchronously
checks `installation-updates/gate.json` before reserving a turn. The controller
acknowledges the gate outside its work loop, binding the acknowledgment to its
PID, boot ID and process start time. Existing action leases can settle normally.
The gate is durable across body/controller restarts and has no implicit timeout.
This participant never changes systemd masks or enabled state: its gate and
stopped controller provide the update pause, and pre-existing masks stay intact.

`installation_source_provider.py` implements protocol 2. It stages exact source,
locked npm dependencies, built screenshot assets and a separate official-SDK
venv. Stable selection requires an actual stable release; the explicitly selected
development channel requires the enrolled successful checks on the exact main
commit. A stable-release absence does not switch channels. The provider refuses
automatic downgrade/unrelated ancestry, and stage fingerprints bind dependency
bytes before cutover. It exchanges only the enrolled app/venv paths plus the
source marker. Rollback retains prior directories and never restores gameplay
state. If a body started for verification must be stopped again before source
rollback, the same participant gate, idle proof and continuity checks apply.
Once listener restoration starts, code rollback is refused.

Task helpers use the generic updater's built-in GitHub `kind: runtime` provider
at a **separate** game `task-helpers/agent-runtime` path. The generic updater
verifies published digests; Minecraft additionally checks static tagged-bound
capabilities before restoring. This is not the agent's selected execution engine.

Create a private owner config outside agent/container mounts. Required fields:

```json
{
  "home": "/absolute/player-home",
  "state": "/absolute/owner-update-state",
  "shared_plans": "/absolute/shared-updater-installation/plans",
  "app": "/absolute/player-home/app",
  "venv": "/absolute/player-home/venv",
  "python": "/absolute/base-python",
  "node": "/absolute/node-22-or-newer",
  "npm_cli": "/absolute/npm-cli.js",
  "task_helper": "/absolute/player-home/task-helpers/agent-runtime",
  "channel": "latest-passing-development",
  "required_checks": ["test"],
  "units": {
    "controller": "acp-minecraft-agent-example.service",
    "body": "acp-minecraft-body-example.service"
  }
}
```

Check names and paths are installation-owned enrollment choices, not chat input.
The source channel is explicitly configured here; the generic scheduler's own
channel must not be described as changing this field automatically. Install the
fixed helper Python files together in an owner directory outside the mutable app,
then run `installation_enrollment.py --config /absolute/config.json --helpers
/absolute/helper-directory --python /absolute/owner-python`. It emits a delta;
it performs no registration write, service operation or policy opt-in. The owner
updater merges that delta without deleting existing components/participants.
Both `minecraft` and `task-helpers` explicitly request
`restart_scope={services:[],instance:false,slack_homes:[]}`. The participant owns
game units; the generic updater owns no game services.

Include `installation_session_probe.py` with the fixed owner helpers. The
participant invokes it using the stable enrolled game `venv/bin/python`, with
only initialize/session-load operations and permission callbacks disabled.
It does not send prompts, maintenance, receipt acknowledgments or session/new.
By default the probe receives a 12-second operation budget within the legacy
30-second participant command limit; this does not change task lifetime, provider settings or action
leases. Lost restore acknowledgment still skips all re-verification and resumes
restoration only; no session load runs after listeners may have resumed.

Before enrollment, the controller must use the stable enrolled
`venv/bin/python` and `app/adapter.py` paths; the body must use the enrolled app.
Configure `task_helpers.command` to the separate helper path once during initial
setup. These bootstrap path changes are not performed by a scheduled update.
Use a source revision containing this admission protocol. Preserve all original
state and policies during that bootstrap, and verify an idle `/installation-state`
response, exact saved session files, unit commands and helper capabilities.
Do not point updater control-plane code/config at the source directory it replaces.

Failure receipts are private and retain a transaction ID and immutable context.
If busy, the generic worker polls prepare before draining Instance. If continuity
changes, no state is rolled back to force a match. Newly observed activity and
appended human inbox entries remain; removed/edited existing pending inputs fail
verification. An external pause wins over restoration. Provider failures after
partial source exchange roll back code only; changed/unknown pointers fail closed.
Exception recovery may require inspecting the recorded discrepancy; it never
silently resets an allowance or replays an uncertain request.

The first installation of admission support itself requires a coordinated
bootstrap; it cannot rely on a gate absent from the installed version. Subsequent
scheduled updates use the installation-owned participant without requesting
operator permission for each ordinary idle update. None of this renews expired
assignments, replays unknown inputs, changes engine families, or enables a
previously disabled work policy. Enabling hourly idle installation is a separate
generic updater policy setting. The provider never prompts a model to resume:
restored controllers continue only authority already valid in their saved state.

### Regenerable source artifacts

Enroll the installation's actual shared updater `plans` directory in
`shared_plans`, outside the game home and Minecraft owner state. Install
`installation_retention.py` alongside the other six owner helpers. This path
is read-only reference evidence, not permission to prune shared plans.

Repeated checks reuse a verified build of the same revision and build inputs.
Failed unreferenced builds are removed immediately, with a compact ownership
and pruning receipt. Other unreferenced stages have a 24-hour grace period
after their last offer, including the interval before the shared worker saves
a returned plan. All retained shared plans, current app/venv links and rollback
targets protect their stages. Obsolete backups are removed only when they
contain managed stage links; original directories and unexpected files remain.
Unmarked historical stages are never adopted or deleted automatically.

Missing, changed or uncertain journals prevent collection; unfinished builds
and transactions also prevent allocating another build. Existing task/session
files are outside the cleanup scope. Edited ready stages remain untouched.
`cleanup-last.json` records the most recent result, and compact artifact
receipts remain after large regenerable directories are pruned. This bounds
repeated busy checks and failed dependency builds, not the size of deliberately
retained shared plans, baseline data or uncertain recovery evidence. Source
checks require this enrollment before hourly installation is enabled.

### Long saved-session verification

Only after verifying an installed shared updater with a 300-second **verify**
hook, an owner may explicitly enroll `session_verification_seconds: 180`. The
default remains 12 for older hosts. Prepare and restore still use their original
30-second command clocks. This opt-in gives initialize plus original-session
load a total 180-second bound and an independent 30-second transport inactivity
bound; healthy history replay can progress without removing either bound.
Cleanup and subsequent continuity checks remain inside the shared verify limit.
No prompt, new session, tool effect, maintenance, task extension or receipt replay
is allowed. Failure stays pre-restore and rollback eligible. Do not enable hourly
installation for long-history sessions until both sides are installed and checked.
