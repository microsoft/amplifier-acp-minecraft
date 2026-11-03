"""Transport/scheduling bridge for the runtime's reusable attention watches."""
import time
from attention import Attention


class Watches:
    def __init__(self, home, config, request, log):
        self.transport=Attention(home,config,log)
        self.config,self.request,self.log=config,request,log
        self.next_poll=0

    async def listing(self):
        return await self.call({'operation':'list'})

    async def call(self,action):
        try:
            return await self.request('/watch',action)
        except Exception as e:
            self.log('watch_bridge_error',operation=action['operation'],error_type=type(e).__name__)
            return None

    async def poll(self):
        if time.monotonic() < self.next_poll:
            return
        self.next_poll=time.monotonic()+self.config.get('interval_seconds',5)
        prepared=await self.call({'operation':'prepare','observe_only':self.config.get('mode','shadow')!='advisory'})
        if prepared and prepared.get('receipts'):
            self.log('watch_evaluated',evaluator='predicate',elapsed_ms=0,receipts=prepared['receipts'])
        if not prepared or 'request' not in prepared:
            return
        token=prepared['token']
        try:
            result,elapsed=await self.transport.evaluate(prepared['request'])
            resolved=await self.call({'operation':'resolve','token':token,'result':result,
                'observe_only':self.config.get('mode','shadow')!='advisory'})
            if resolved is None:
                await self.call({'operation':'abandon','token':token})
                return
            # Exact request/result are needed for replay; private service journal.
            self.log('watch_evaluated',request=prepared['request'],result=result,elapsed_ms=elapsed,receipts=resolved.get('receipts',[]))
        except Exception as e:
            self.log('watch_error',error_type=type(e).__name__)
            await self.call({'operation':'abandon','token':token})

    async def pending(self):
        listing=await self.listing()
        return [w['notification'] for w in (listing or {}).get('watches',[]) if w['status']=='triggered']

    async def managed(self):
        listing=await self.listing()
        # An unavailable watch store must not silently substitute a broader policy.
        return listing is None or any(w['status'] in ('armed','triggered') for w in listing['watches'])

    async def acknowledge(self,notifications):
        for item in notifications:
            await self.call({'operation':'ack','id':item['id']})
