# Reading historical input outcomes

Upgraded installations retain the original workshop journal. Its input IDs, historical admissions, Stop state, limits, pending work and uncertain effects keep their original meaning. Owner inspection is read-only. An unknown outcome does not establish failure or make the old request eligible for another send.

New public chat uses a durable inbox and an exact event identity. The controller claims the event before sending it to its bound session. After an interrupted delivery it leaves the claim intact. A tool action has its own operation ID and reports its own result. The two identities identify different events.

See [installation inputs](installation-inputs.md) for private caller receipts and [the adapter reference](adapter-reference.md) for public chat and world tools.
