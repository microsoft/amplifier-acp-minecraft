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
