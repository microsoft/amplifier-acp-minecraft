"""ACP observations, not guessed provider health or an elapsed turn budget."""
import asyncio
import time


async def await_terminal(pending, timeout=5):
    """A completed local future can be transport loss, not a prompt response."""
    done, _ = await asyncio.wait({pending}, timeout=timeout)
    if not done:
        return {'terminal_observed': False, 'outcome': 'unknown'}
    if pending.cancelled():
        return {'terminal_observed': False, 'outcome': 'local_cancelled'}
    error = pending.exception()
    if error is not None:
        return {'terminal_observed': False, 'outcome': 'prompt_error',
                'error_type': type(error).__name__}
    result = pending.result()
    return {'terminal_observed': True, 'outcome': 'prompt_response',
            'stop_reason': result.get('stop_reason', 'unknown'),
            'unsettled_tool_count': len(result.get('unsettled_tools', []))}


class PromptLifecycle:
    def __init__(self, observe, *, clock=time.monotonic, quiet_seconds=180):
        self.observe, self.clock, self.quiet_seconds = observe, clock, quiet_seconds
        self.started = self.last_progress = clock()
        self.phase = 'awaiting_agent'
        self.quiet = False
        self.compactions = {}
        self.tools = {}

    def update(self, item):
        kind = item.get('sessionUpdate')
        progressed = False
        if kind in ('agent_message_chunk', 'agent_thought_chunk'):
            progressed = bool(item.get('content', {}).get('text'))
            if progressed:
                self.phase = 'agent_output'
        elif kind in ('tool_call', 'tool_call_update'):
            identity, status = item.get('toolCallId'), item.get('status')
            if isinstance(identity, str) and status in ('pending', 'in_progress', 'completed', 'failed'):
                progressed = self.tools.get(identity) != status
                self.tools[identity] = status
                self.phase = 'tool_running' if status in ('pending', 'in_progress') else 'awaiting_agent'
        elif kind == 'compaction_update':
            identity, status = item.get('compactionId'), item.get('status')
            if isinstance(identity, str) and status in ('in_progress', 'completed', 'failed', 'cancelled'):
                progressed = self.compactions.get(identity) != status
                self.compactions[identity] = status
                self.phase = 'compacting' if status == 'in_progress' else 'awaiting_agent'
                if progressed:
                    self.observe('compaction_status', compaction_id=identity, status=status,
                                 evidence='acp_session_update', prompt_settled=False)
        # Empty receipts, usage changes, repeated status, unknown extensions and
        # keepalives are not evidence of reasoning progress or effect completion.
        if progressed:
            self.last_progress = self.clock()
            if self.quiet:
                self.observe('planner_progress_resumed', phase=self.phase)
            self.quiet = False

    def sample(self):
        silence = max(0, self.clock() - self.last_progress)
        if silence >= self.quiet_seconds and not self.quiet:
            self.quiet = True
            self.observe('planner_progress_unknown', phase=self.phase,
                         quiet_seconds=round(silence), evidence='no_recent_acp_progress',
                         provider_health='unknown', cancelled=False)
        return {'phase': self.phase, 'quiet': self.quiet, 'provider_health': 'unknown'}
