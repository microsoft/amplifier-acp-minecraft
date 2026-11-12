# Native connector packages

Native packages contain private Node and Python runtimes, the pinned official
Python ACP SDK, the connector and its dependency graph, and the screenshot
renderer/browser, and a separately pinned pure task-helper executable. Building requires developer tools; running a built package
does not require installing Node, Python, Git, npm or a compiler.

The native workflow builds separately on Linux x64/ARM64, macOS Intel/Apple
silicon and Windows x64/ARM64. It verifies package digests, actual SDK initialize
and original-session load, initialize-only for an unused connection, body
fixtures and a real browser rendering fixture. Windows x64 CI uses Windows
Server; this is not Windows 11 desktop first-run evidence. Linux browser system
libraries are installed separately on the runner; their presence is a runtime
prerequisite, not something the archive has bundled.

These are candidate connector artifacts. Native startup registration,
installation/connection lifecycle, protected-home handling and updater rollback
must also pass before claiming a supported native installation. A successful
package build alone does not establish those behaviors. Existing Linux
installations retain their enrolled source provider and service lifecycle.

## Build and verify

Run on the desired native target, using Python 3.12 or newer:

```text
python ops/native/build_bundle.py --output bundle --cache runtime-cache
```

`ops/native/runtime-lock.json` pins each downloaded runtime archive by SHA-256.
The SDK is installed from its immutable upstream commit and its actual
`direct_url.json` is checked. `manifest.json` records source cleanliness,
upstream runtime provenance, installed Python versions and every package file
or internal link. Do not publish a dirty-source bundle. No personal installation,
credentials, world or saved session is copied into the package.

Run `minecraft doctor` (`minecraft.cmd doctor` on Windows) from the extracted
package for read-only verification. The fixed `body --home <absolute-path>` and
`controller --home <absolute-path>` entry points use the private runtimes; they
require an already prepared, explicitly authorized connection home. They do
not create accounts, register context, accept work or create a world.

The verification script runs disposable fixtures using the packaged interpreter:

```text
bundle/python/bin/python3 -I ops/native/verify_bundle.py --bundle bundle --source . --receipt native-result.json
```

On Windows use `bundle/python/python.exe`. Keep the exact receipt and manifest
with each tested archive. The fixture does not contact a real game or model.
Server installation, Java, accounts, edition gateways and LAN discovery remain
separate: follow the [server setup guide](server-setup.md).

## Pure task helper

`manifest.commands.task_helper` resolves the bundled helper below the validated
package root. Native setup can explicitly configure `task_helpers.command` to
that absolute executable; it is independent of the selected ACP engine. The
package does not replace an engine, select a model, renew work or rewrite an
existing configuration. Existing enrolled installs keep their separately owned
helper update component.

The six-target fixture invokes the actual packaged `helper-capabilities`,
`continuation-v2` and `watch-v2` commands without a model or agent home. It checks
explicit unbounded tasks, bounded watch lifetime, Stop, unknown-bound refusal
and unchanged stored watches after invalid input. No maximum-number sentinel
or task conversion is introduced.

## Native lifecycle integration

The candidate package can include the separately reviewed Constellation native
installation driver and its Python binding. Build with both `--native-shared`
(the exact checkout pinned in `ops/native/shared-driver-lock.json`) and
`--native-driver` (the binary built for this target). The package records both
source and binary identity. This is an explicit backend; existing Linux
installations do not switch merely because it is present.

Setup uses `installation_native_setup.profiles` to describe fixed body,
controller and original ACP endpoint commands. The shared installer supplies
protected owner roots and configuration; `register_no_start` registers those
exact service definitions without starting, unpausing, changing context access,
or creating an engine session. Keep the updater interpreter and helper code
outside the mutable game home. The controller and session probe may use the
verified private Python copy under `home/venv`, so source/environment exchanges
retain their stable invocation paths. No host-wide Python or Node is required.

`installation_enrollment.py` emits a registration delta for the explicit
`native_platform` configuration, using isolated Python and fixed entry points.
It does not install that delta or enable a schedule. The Minecraft source and
pure task-helper components remain separate, with empty shared restart scopes;
the participant owns game service admission, continuity checks, original-session
verification, and restoration. Connection controls use the same backend and
retain the acknowledged quiescence/readiness handoffs. An unknown operation is
not permission to retry it.

Optional `native_platform.data_journals: 1` selects the shared data reader and
replacement writer together. Enrollment requires exact `private_data_read: 1`
and `private_data_publication: 1` advertisements and both `storage.read_data`
and `storage.write_data` operations. This option is not inferred from Windows
or enabled by upgrading a binary. Qualify the paired reader/writer and combined
driver before enrolling an installation.

The fixed selection covers direct JSON children of owner-state `transactions`,
`connections`, `provider-receipts`, `native-source-receipts`, and
`artifact-receipts`, plus `active.json` and `cleanup-last.json`. In the game home
it covers `app-source.json`, the installation gate/controller acknowledgment,
and `installation-connections/state.json`. Full workshop history, credentials,
driver configuration, package manifests/fingerprints, and independently owned
updater plans retain their separate read/publication paths. Reference collection
hashes and parses the same read snapshot.

Selected journals have an explicit 1 MiB serialized limit: oversized reads
refuse, and oversized writes refuse before directory creation or publication.
Audit existing and projected receipt sizes, including captured continuity
baselines, before enrollment. No truncation, empty-state fallback, or automatic
switch back to strict I/O is allowed. Absence remains `FileNotFoundError`; empty
or invalid JSON, owner/refusal/read errors, and lost transport remain errors.
Unwind a failed Session's locks before fresh read-only reconciliation; an old
`with` block does not retain ownership and uncertainty never permits republishing.
The data reader permits Windows delete sharing; other processes reading these
journals still require their own compatible-handle qualification.

Native source updates use the stable channel's exact target archive, published
digest and source tree. They verify the official SDK's immutable provenance and
stage privately before stopping services. They do not run Git, npm or pip on
the destination. A base Python, Node, or shared-driver change requires its own
installation migration rather than silently changing those enrolled helpers.
Source/environment publication uses two journaled native exchanges, retaining
rollback targets; it is not an atomic pair. Restore begins only after the
candidate's original saved session loads successfully, or initialize succeeds
for a genuinely unused connection. Neither check prompts the model.

The complete domain fixture is `ops/native/verify_lifecycle.py`. It uses actual
native services on each target, a disposable body and deterministic ACP endpoint,
and exercises no-start registration, source apply/verification/rollback,
shared-component admission, Connect/Disconnect, and lost terminal replies.
Its receipt separately records original loads, absence of prompts/new sessions,
and disposal of its own test services. Keep failures as well as passing receipts.

Native end-user enrollment remains a candidate until the combined target tests,
protected initial-root setup, and reference-aware native staging cleanup are
qualified together. Do not enable automatic source updates from package-build
success alone, or substitute ordinary Windows directory deletion for the shared
owner's protected cleanup operation.


### Candidate native staging cleanup

Native regenerable-tree cleanup is a separately negotiated capability. A reviewed
owner configuration may select `native_platform.regenerable_tree_removal: 1` only
when the installed shared driver advertises `regenerable_tree_removal: 1` and
`tree.inspect`/`tree.remove`. Setup then enrolls exactly the existing `state/stages`
and `state/backups` subdirectories under the installation lock. This does not
modify an existing protected driver configuration or enable cleanup on older
installations. The directories must exist before protected configuration bootstrap.

Minecraft still selects only marked, unreferenced regenerable artifacts. Current
app/venv, baseline directories, retained shared plans, native rollback pointers
and unsettled journals remain protected. Rooted inspection supports stage
allocation/reuse without relying on Python recursive-deletion support. Before
removal Minecraft records the exact shared identity in its durable pruning intent;
the shared driver performs removal under the same Session installation lock.
There is no connector fallback to platform deletion commands.

A lost transport or unknown removal outcome leaves the intent unresolved. Unwind
the Session before any recovery write, then acquire a fresh lock for read-only
inspection. Neither a remaining tree nor a replacement authorizes redispatch.
When the driver explicitly advertises `regenerable_tree_observation: 1` and
`tree.observe`, Minecraft records the complete observed scope and exact profile
name/entry in the same pruning intent before removal. A later invocation may
settle only that intent when a fresh locked observation has exactly the same
scope and an absent entry, with current reference and transaction guards still
passing. It records `same_scope_absence`; it never repeats removal. Changed
root/profile/lock mapping, a remaining or replaced entry, unknown observations,
and legacy intents without the saved scope remain unresolved. Older drivers
still support removal, but their bare-null inspection cannot establish recovery.

The shared cleanup candidate and combined six-platform consumer tests must be
qualified before enrollment. Local contract tests or a disposable Linux run alone
are not release or live-installation evidence.


The source-provider entrypoint captures one monotonic 600-second invocation
deadline before setup and lock acquisition. Its optional native cleanup selects
at most 120 seconds for one `tree_remove(..., timeout=...)`, reduced to the
remaining invocation time minus a 60-second settlement/close/output reserve.
With less than 30 seconds available after that reserve it defers before dispatch.
The allowance is checked before journaling and again immediately before removal;
it is never reset between artifacts. If time expires between those checks, the
existing pruning intent remains conservative and no removal is dispatched.
Other calls retain the Session default; service, prepare, verify and restore
budgets do not change. Consumers without an enclosing cleanup deadline keep the
Session default. The extended per-call API requires the separately qualified
shared candidate; unit budget tests alone do not qualify a Windows removal.
