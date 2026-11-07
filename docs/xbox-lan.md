# Xbox / Bedrock LAN access

This adapter controls Java players. Xbox clients use Bedrock and need a separate
human gateway, normally Geyser with Floodgate for account linking. The gateway is
server infrastructure: installing/updating the Python adapter does not install
it, configure the firewall, or make a console discover a world.

## Requirements and topology

- A Java world compatible with the selected Geyser version. Preserve the existing
  authenticated human path, player UUID/account links and allowlist.
- A Bedrock build supporting the console's protocol. Bedrock 26.60 requires
  NetherNet; a legacy RakNet LAN advertiser/selector alone is insufficient.
- Built-in signaling needs its configured TCP port; WebRTC gameplay needs its
  configured UDP port. If those differ, allow both. Advertise the actual reachable
  address, not container loopback, an unrouted private address or only a VPN name.
- LAN listing additionally requires discovery replies on UDP **7551**. Same-LAN
  broadcasts must reach the host: check wireless client isolation, guest networks,
  VLAN boundaries and host/container networking. A routed VPN does not carry LAN
  discovery simply because unicast Java connections work.
- Keep the agent-only offline/trusted proxy loopback/private. Never point a human
  console at it or disable signed login to make a connection succeed.

Example layout (choose unused ports appropriate for your installation):

| Purpose | Example | Access |
| --- | --- | --- |
| Human Java gateway | TCP 25565 | Approved human clients |
| Bedrock built-in signaling | TCP 19132 | Approved human clients |
| Built-in WebRTC gameplay | UDP 19133 | Same approved clients |
| Bedrock LAN discovery | UDP 7551 | Intended LAN only |
| LAN WebRTC gameplay | UDP 19134 | Intended LAN only |
| Agent proxy / Java backend | Installation-specific | Private; never console-facing |

One process owns UDP 7551 on a host. Separate hosts on one LAN can each advertise
a distinct world name. Multiple worlds on the same host need a gateway/selector
that actually supports routing them; changing Java or Bedrock gameplay ports does
not create another discovery socket. Container deployments need both discovery
broadcast access and fixed UDP gameplay routing; exposing a TCP dashboard is not
sufficient.

See [Geyser's NetherNet guidance](https://geysermc.org/blog/preparing-for-nethernet/)
and [current setup documentation](https://geysermc.org/wiki/geyser/setup/).

## Known 26.60 discovery and Xbox compatibility gap

As checked on November 7, 2026, official Geyser **2.12.1-b1288**, source
`50360e396b08c10dac4dfb78213dcb0126b75f90`, supports address-based NetherNet but does
not start the LAN discovery listener. See
[upstream issue #6853](https://github.com/GeyserMC/Geyser/issues/6853).
The Xbox LAN path also needs a compatible signaling answer and a nonce bound to
its signed login. An open port or a successful generic transport handshake does
not prove an Xbox authenticated join.

The optional [pinned compatibility patch](../ops/geyser-lan/geyser-50360e3-lan.patch)
was exercised with 158 Geyser core tests, disposable transport fixtures, cross-host
LAN broadcast discovery/ICE/DTLS/SCTP, and a real Xbox 26.60 discovery and join.
It is **not an upstream release**, a universal patch for other versions, or an
adapter runtime dependency. Prefer a subsequently verified upstream solution;
reevaluate this patch before replacing its base. It includes a test-only scoreboard
bootstrap correction so the base's full core suite can run in isolation.

The patch:

- Opts into official Cloudburst LAN discovery APIs; it does not replace protocol framing.
- Uses a required fixed LAN ICE port and a fresh advertised nonce per gateway lifetime.
- Omits the incompatible SDP identity line from **LAN-only** answers. Built-in HTTP
  signaling keeps its existing behavior.
- Accepts the unbound LAN transport only after the existing service-chain and
  client-data signature checks pass and the signed nonce matches. Non-LAN,
  unsigned, wrong/missing nonce, and conflicting binding cases still fail. Keep
  `advanced.bedrock.validate-bedrock-login: true`.

### Build and package the pinned patch

Use a separate clone, Java 25, the pinned Geyser source and its submodules. A
regular clone also avoids the upstream template task's Git-worktree lookup issue.
The Gradle build fetches dependencies; run it in a disposable build environment.
No server or credentials are needed.

```sh
# Set this to your existing amplifier-acp-minecraft checkout.
ADAPTER_REPO=/path/to/amplifier-acp-minecraft
git clone https://github.com/GeyserMC/Geyser.git geyser-lan-build
cd geyser-lan-build
git checkout 50360e396b08c10dac4dfb78213dcb0126b75f90
git submodule update --init --recursive
git apply --check "$ADAPTER_REPO/ops/geyser-lan/geyser-50360e3-lan.patch"
git apply "$ADAPTER_REPO/ops/geyser-lan/geyser-50360e3-lan.patch"
./gradlew :core:test :velocity:shadowJar :standalone:shadowJar --no-daemon
curl --fail --location \
  https://download.geysermc.org/v2/projects/geyser/versions/2.12.1/builds/1288/downloads/velocity \
  --output Geyser-Velocity-official.jar
python3 "$ADAPTER_REPO/ops/geyser-lan/package_overlay.py" \
  --platform velocity --base Geyser-Velocity-official.jar \
  --built bootstrap/velocity/build/libs/Geyser-Velocity.jar \
  --out Geyser-Velocity-lan.jar > lan-build-receipt.json
```

The packager rejects any base other than the exact official artifact (Velocity
SHA256 `945a7ece089f44118ba85848ceb7a6e054fe65c26f5525dd7f548b44e5b42175`).
It overlays only the five reviewed class families and checks every other original
entry byte-for-byte, avoiding unrelated snapshot-dependency upgrades in a rebuilt
fat JAR. It records all replacement class hashes inside the output and prints the
resulting artifact hash. Inspect that receipt and retain the patch/build/test
provenance. This does not promise byte-identical generated ZIP timestamps across
builds or install the output automatically.

For Standalone use the corresponding `standalone` download/platform and
`bootstrap/standalone/build/libs/Geyser-Standalone.jar`; its accepted official
base SHA256 is `fcd8cd26f3e4a1180ee3828b6c63ed3b90e78c99c7ccc2cbba3b12f303d705b9`.
Other distributions are not packaged by this helper.

### Configure, install and verify

1. Capture the current gateway binary/configuration, firewall, player connections
   and rollback paths. Coordinate the human gateway restart with its owner.
   Preserve the world, agent bodies/controllers, tasks, sessions, inventories,
   unknown receipts and account linking; this change grants no agent work.
2. Keep normal NetherNet configuration, for example:

   ```yaml
   bedrock:
     address: 0.0.0.0
     port: 19132
     webrtc-port: 19133
     transport: both
     signaling:
       mode: builtin
       advertise-addresses: ["YOUR_LAN_IP:19133"]
       stun-discovery: false
   advanced:
     bedrock:
       validate-bedrock-login: true
   ```

   Merge those settings into the existing configuration; do not overwrite Floodgate
   keys, account links, backend addresses or other existing settings.
3. Install the checked compatibility JAR and add JVM options **before** `-jar`:
   `-DgeyserLanDiscovery=true -DgeyserLanIcePort=19134`.
   The default discovery bind is `0.0.0.0` to receive broadcasts; the optional
   `-DgeyserLanBind=...` changes it. These properties belong to this patch; an
   unpatched JAR may silently ignore them. The LAN ICE port must differ from
   UDP 7551 and the configured built-in WebRTC port.
4. Allow UDP 7551 and the fixed LAN ICE port only from the intended physical LAN
   (and necessary local probes), then deny other sources, including unintended IPv6
   access. Persist the rules across reboot. Preserve the existing approved Java,
   Bedrock, VPN and administration paths. Do not add Internet/router forwarding
   for same-LAN access. Apply restrictive rules **before** starting the listener.
5. Restart only the affected human gateway. Verify the new LAN startup message,
   UDP listener and advertised world name/version from another LAN host. A v7
   discovery payload carries 26.60/protocol 2225; the legacy v6 payload omits these
   fields, so a library's default version label is not evidence of incompatibility.
6. Test a real Xbox: verify the world is visible, authenticate, join and leave.
   Account permissions/allowlisting can still reject a valid transport connection.
   Menus differ by console/version; don't require an Add Server button or promise
   a specific tab name. Separately check the existing Java route and agent chat.

If the gateway fails startup or compatibility checks, stop that gateway, restore
its original JAR/options/configuration and restart it. Remove only the new firewall
rules if reverting their persistent configuration. Do not roll back the world or
replay agent inputs. Preserve a concise receipt of installed hashes, unchanged
services/state, network checks and the actual console result.
