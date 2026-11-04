"""Cheap conversation admission, using the shared runtime participation policy.

No fixed name requirement, model fallback, task creation, or domain plan.
Only changed pending conversation evidence can cause a decision-service call.
"""
import asyncio
import hashlib
import json
import time
from attention import Attention


class ConversationAttention(Attention):
    def __init__(self, home, config, log):
        super().__init__(home, config, log)
        self.ledger = home/'participation-calls.json'
        self.calls = json.loads(self.ledger.read_text()) if self.ledger.exists() else []
        self.retry_after = 0

    async def consider(self, request):
        proposal = await request('/participation')
        if not proposal or time.time() < self.retry_after:
            return
        # Independent players settle at slightly different times; a fresh read
        # includes intervening replies so the policy can avoid talking over them.
        name = proposal['context']['agent']['id']
        delay = .3 + int(hashlib.sha256(name.encode()).hexdigest()[:4],16) % 900 / 1000
        await asyncio.sleep(delay)
        proposal = await request('/participation')
        if not proposal:
            return
        now = time.time()
        self.calls = [t for t in self.calls if t > now-3600]
        if len(self.calls) >= self.config.get('max_participation_calls_per_hour',600):
            self.retry_after = min(self.calls)+3600
            self.log('participation_capacity',resume_at=self.retry_after)
            return
        self.calls.append(now)
        self.ledger.write_text(json.dumps(self.calls)); self.ledger.chmod(0o600)
        self.log('participation_decision_attempt',trigger_id=proposal['context']['trigger_id'],signature=proposal['signature'])
        try:
            result, elapsed = await self.evaluate(proposal['context'],'participate')
            if (result.get('policy') != 'conversation-participation-v1'
                or result.get('trigger_id') != proposal['context']['trigger_id']
                or result.get('conversation_id') != proposal['context']['conversation_id']
                or result.get('action') not in ('engage','hold')):
                raise ValueError('Invalid participation result')
            receipt = {'time':now,'signature':proposal['signature'],'context':proposal['context'],
                       'result':result,'elapsed_ms':elapsed}
            path=self.home/'participation.jsonl'
            if path.exists() and path.stat().st_size>8*1024*1024:
                path.replace(self.home/'participation.previous.jsonl')
            with path.open('a') as f:
                f.write(json.dumps(receipt)+'\n')
            path.chmod(0o600)
            applied = await request('/participation',{'signature':proposal['signature'],'action':result['action']})
            self.log('participation_applied',**applied,judgment=result.get('judgment'),elapsed_ms=elapsed)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.retry_after = time.time()+5
            self.log('participation_unavailable_or_stale',error_type=type(e).__name__,trigger_id=proposal['context']['trigger_id'])
