# Minecraft connection and world tools

Players, agent designers and installation owners rely on this agreement. Minecraft owns observations, conversation transport and the effects of operating one player in one world. The agent owns attention, planning, task acceptance, collaboration, memory, reminders and follow-through. Brian approved this division for the Minecraft connector on November 22, 2026.

## Conversation and context

Deliver game messages with stable identities, speaker attribution, audience and world. Keep public conversation, whispers and private installation input within their intended audiences. An agent may receive a message and remain silent. Sending a message is an explicit act. Transport acceptance establishes only what the transport observed. Use the shared [interaction agreement](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/interaction.md) for audience and participation semantics.

Expose the player's position, inventory, nearby entities and visible blocks as observations with their actual scope. A scan of loaded terrain can miss distant resources. An agent chooses when to look again. A quiet world generates no planning prompts. Agent-owned scheduling can invoke the same tools between messages. An authenticated `wake({id,note})` asks for one immediate prompt on the saved game session. The agent chooses when to ask. The prompt identifies an agent wake and carries its ID, note and request time. It carries no player attribution or new authority. Acceptance records the request before replying. A repeated ID with identical input queues nothing further, including after an unknown delivery. Stop cancels queued wakes, and a claimed wake with an unknown outcome requires reconciliation.

## Actions

An authenticated agent with the installed capability can invoke game tools without opening a Minecraft turn, acquiring a work lease or presenting a task or message as justification. The agent decides how to use an instruction. The body enforces its configured access, operator Stop, physical reach, resource availability and conflicts on the one avatar. A compound action such as walking a path or placing a supplied pattern executes the agent's explicit request and reports partial progress.

A consequential call has an operation identity. Record it before dispatch. Reusing that identity with different arguments is an error. On a repeated call with identical arguments, return the existing disposition. After a disconnect the caller can inspect the outcome, including uncertainty. A missing acknowledgement supplies no authority to repeat an effect. A genuinely conflicting operation can remain unavailable while unrelated observations and safe work remain accessible. Report observed arrival, inventory change or block state at the scope actually checked.

## Continuity and compatibility

Bind a player, saved ACP session and credentials to the intended installation and world. Preserve these bindings, existing work, Stop state and evidence of pending or uncertain effects through restart or upgrade. Historical records remain available to their authorized audience. Catch-up must distinguish history from fresh input. Loading a session, refreshing transport access or reconnecting a body must never turn old instructions into new prompts or execute old actions.

Offer the game connection through [ACP](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/engine-compatibility.md) and discoverable game tools through MCP. Operation and message identifiers belong to the connection. Agent-side scheduling, staffing, budgets, state machines and model turns remain decisions for each agent implementation. Installation lifecycle and owner controls follow the shared [installation agreement](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/installations.md).

## How to judge it

Give two real agents with different internal designs the same connector. In a shared test world each can receive conversation in its intended audience, inspect the world, decide independently and use an authorized action. Verify what another player or the server observed. Leave the world quiet and check that the connector issues no continuation prompt. Interrupt a consequential operation and reconcile its identity across reconnect. Check the original session, inventory, work and outstanding receipts before and after migration. Record which of these checks ran and what remains unverified separately from this agreement.
