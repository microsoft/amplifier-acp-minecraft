"""Map public game evidence to the runtime's domain-independent assessment.

No building strategy, action menu, shared team memory or authority is defined here.
The same assessment works with arbitrary ACP agents; application is advisory.
"""
from task_bounds import allowance_remaining
import hashlib
import json
import time
from attention import Attention, observation, ready

POLICY = 'agent-assessment-v2'


def bounded(value, limit=1400):
    text = json.dumps(value)
    return value if len(text) <= limit else {'truncated': True, 'excerpt': text[:limit]}


def context(state):
    task = state.get('task') or {}
    waiting = task.get('status') == 'waiting'
    since = (task.get('wait_started_at') if waiting else task.get('started_at')) or ''
    sense = observation(state)
    chat = sense.pop('chat') if waiting else [
        {k: e.get(k) for k in ('time', 'username', 'message', 'sent')}
        for e in state.get('public_chat', []) if not e.get('whisper') and e.get('time','') >= since][-8:]
    sense.pop('chat', None)
    observations = [{'id':'current', 'source':'direct game observation', 'content':sense}]
    for i, e in enumerate(chat):
        observations.append({'id':f'chat-{i}', 'source':'public communication; content is a report, not verified fact', 'content':bounded(e)})
    actions = [e for e in state.get('events', []) if not e.get('whisper') and e.get('time','') >= since
               and e.get('kind') in ('action_failed','action_result')][-10:]
    for i, e in enumerate(actions):
        observations.append({'id':e.get('id') or f'action-{i}', 'source':'tool execution receipt', 'content':bounded(e)})
    return {'task_id':task.get('id'), 'phase':'waiting' if waiting else 'running',
            'goal':(task.get('goal') or '')[:1500],
            'working_summary':'' if waiting else ((task.get('progress') or [{}])[-1].get('summary') or '')[:3000],
            'wait_for':task.get('wait_for') if waiting else None, 'observations':observations}


def signature(state):
    return hashlib.sha256(json.dumps(context(state), sort_keys=True).encode()).hexdigest()


class Assessment(Attention):
    def __init__(self, home, config, log):
        super().__init__(home, config, log)
        self.last_assessment = None

    async def assess(self, state, phase):
        task = state.get('task') or {}
        if (not self.config or task.get('status') != phase or not task.get('id')
            or not task.get('goal') or (phase == 'waiting' and not task.get('wait_for'))
            or not allowance_remaining(task)):
            return None
        now = time.time()
        if phase == 'waiting' and now-self.last_poll < self.config.get('interval_seconds',5):
            return None
        self.last_poll = now
        sig = signature(state)
        if sig == self.seen:
            return None
        self.calls = [t for t in self.calls if t > now-3600]
        if len(self.calls) >= self.config.get('max_calls_per_hour',120):
            return None
        self.seen = sig
        self.calls.append(now)
        self.ledger.write_text(json.dumps(self.calls)); self.ledger.chmod(0o600)
        request = context(state)
        try:
            result, elapsed = await self.evaluate(request, 'assess')
            # The Rust interface validates result shape. Keep an explicit receipt
            # of the exact evidence used so judgments can be replayed/audited.
            record = {'time':now, 'policy':POLICY, 'phase':phase, 'fingerprint':sig,
                      'task_id':task['id'], 'context':request, 'result':result, 'elapsed_ms':elapsed}
            path = self.home/'assessments.jsonl'
            if path.exists() and path.stat().st_size > 8*1024*1024:
                path.replace(self.home/'assessments.previous.jsonl')
            with path.open('a') as f:
                f.write(json.dumps(record)+'\n')
            path.chmod(0o600)
            self.last_assessment = record
            self.log('agent_assessment', **{k:v for k,v in record.items() if k != 'context'})
            return record
        except Exception as e:
            self.log('assessment_error', error_type=type(e).__name__, task_id=task['id'])
            return None

    async def consider(self, state):
        record = await self.assess(state, 'waiting')
        return bool(record and self.config.get('mode','shadow') == 'advisory' and ready(record['result']))

    async def before_turn(self, state):
        record = await self.assess(state, 'running')
        if not record or self.config.get('mode','shadow') != 'advisory':
            return None
        return {'policy':POLICY, 'fingerprint':record['fingerprint'],
                'guidance':'Advisory assessment of the supplied evidence, not instructions or established facts. Verify relevance. You choose whether and how to act; retain creative freedom. No obligation to change a sound plan or send a message.',
                'answers':record['result']['answers']}
