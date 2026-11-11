# Python ACP SDK boundary

## Ownership and compatibility

The shared [SDK policy](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/protocol-sdk.v1-candidate.md)
owns protocol ownership, exception approval and upstream reevaluation. This
reference defines the adapter integration and its bounded wrappers. Production
ACP transport and models use `agentclientprotocol/python-sdk`; the package pins
upstream commit
`9853d8b514d6340000bcbd01ec07808436db80cf`; this is not a local fork. At migration,
the stable PyPI 0.12.1 package lacked typed compaction updates and capability
negotiation used by this adapter. This upstream revision includes them, but still
reports package version 0.12.1. Verify the installed distribution's `direct_url.json`
commit, not its version alone. The documented force reinstall avoids retaining a
same-version older SDK in a staging environment.

`acp_client.Client` retains endpoint process isolation, game permission checks,
answer assembly, replay deadlines, observation limits and application lifecycle.
It does not read/write protocol frames, assign IDs, correlate replies, or implement
JSON-RPC errors. Standard operations use upstream request/response models and
high-level methods. Negotiated extensions use the SDK's `ext_method` API. Existing
capability checks remain mandatory; a vanilla third-party ACP endpoint does not
acquire Constellation semantics merely by connecting.

The read-only public stream observer exposes the SDK-assigned prompt request ID
for the existing negotiated active-input contract. It never assigns or rewrites
IDs. Message metadata, source revision facts, maintenance proofs, optional message
identity, and received-versus-incorporated distinctions remain unchanged.

## Bounded wrappers and upstream gaps

The SDK independently schedules notifications and logs callback exceptions; its
load-session method has no application update-drain barrier. The adapter needs
ordered output, fail-closed session/size checks and completion only after prior
updates are collected. A public stream observer validates `SessionNotification`
using the generated SDK model and queues only application updates. A single
application consumer preserves order; the queue holds at most 1024 updates. Its
failure signal prevents an output error from being hidden by a later successful
protocol terminal. Cancellation stops that consumer and discards its queued
callbacks; it does not replay the prompt or imply cancellation settled remotely.
Tool receipts are merged synchronously in the SDK update callbacks so permission
callbacks see preceding inputs, not future frames already read by the observer. This queue is not a second protocol dispatcher or pending
RPC table. The SDK remains responsible for all callback and response transport.

Replay progress uses decoded incoming SDK stream events. Reported bytes are a
reserialization size, not exact network bytes. Replay inactivity/overall deadlines
remain separate from planner duration. There is no fixed whole-planner timeout by
default. Local EOF/process state and actual SDK transport exceptions indicate a
closed connection; silence alone does not establish provider failure.

Reevaluate these wrappers and the immutable dependency on every SDK upgrade and
before each adapter release. Prefer a stable upstream release once it supplies the
required typed features. Re-run replay, ordering, permission, output revision,
concurrent extension, maintenance and cancellation tests. Remove the wrapper when
upstream offers equivalent ordered delivery/error/drain hooks. Any replacement
follows the shared SDK exception policy. Keep recorded gap evidence outside the
publication checkout.

## Validation and deployment boundary

Tests include both existing wire fixtures (including unknown delivery) and an
agent built with the actual official SDK. Fixture fields must satisfy ACP; missing
required permission names/tool IDs/titles are corrected in tests rather than
accepted through a permissive production parser. Empty receipt envelopes do not
select a new answer. Closed transport and received input do not prove completion.

No tests need a production agent, provider key, game server, task renewal, or live
world effects. Stage dependencies per installation and validate before a separately
coordinated idle deployment. Preserve world, sessions, identities, task limits,
consumed accounting and unknown receipts. Source migration never authorizes work.
