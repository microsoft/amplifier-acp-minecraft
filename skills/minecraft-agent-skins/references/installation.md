# Installation and evidence

Determine whether the player uses an authenticated Java account skin, server-
managed skin, or Bedrock appearance forwarded through a bridge. Inspect the current
mapping/component: offline names, account UUIDs and linked Bedrock UUIDs are not
interchangeable. Do not change authentication mode or grant operator privileges.

For an account, use its supported upload with the matching classic/slim model.
For a server-managed skin, use the installed component's documented import and
refresh path. Java player-info textures may require a signed property; copying
a PNG is not necessarily sufficient. Retain the prior mapping for targeted rollback.

## Signing when required

MineSkin's queued signing API is one previously used option, not a required
identity service. Recheck current authentication, limits and response shape:

- [Queue skin generation](https://docs.mineskin.org/docs/mineskin-api/queue-skin-generation/)
- [V2 migration and models](https://docs.mineskin.org/docs/guides/migrating-to-v2/)
- [Rate limits](https://docs.mineskin.org/docs/guides/rate-limits/)

Upload only the final texture, not a photo or reference portrait. Record the
external artwork upload; unlisted visibility is not a confidentiality guarantee.
Use authorized service access; keep credentials outside the repository/transcripts.

Persist submission/job receipts before polling. Resume a known job after a timeout;
do not blindly resubmit an ambiguous upload. Bound retries and respect rate limits.
Acceptance is queued work, not signing success. Require a successful terminal
result with the texture value/signature expected by the installed component.

When permitted, download the published texture and compare visible pixels,
dimensions and model. Re-encoding can change PNG bytes without changing pixels;
RGB beneath fully transparent pixels is not visible. Report differences honestly.

## Refresh and verify

Prefer supported refresh. If reconnecting is necessary, verify an idle boundary
and preserve identity, session, task binding, deadline, consumed budgets and mode.
Cosmetic work does not authorize expired construction or restarting other players.

Verification has distinct levels:

1. **Artifact:** valid texture/model and reviewed mapped appearance.
2. **Server delivery:** correct player's texture property matches the intended
   signed texture (or documented equivalent).
3. **Client appearance:** a real client sees the intended features after refresh.
   Compare similar lighting/distance. Check Java and bridged Bedrock separately
   when in scope; packet success does not prove every bridge/cache renders it.

Report the strongest completed level and remaining checks. Keep bindings,
timestamps, hashes and receipts private. Do not claim another person's
installation was checked without actual evidence.
