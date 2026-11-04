"""Source facts and admission delivery; shared social policy belongs to the ACP host."""
import time

META='com.microsoft.amplifier.attention'
METHOD='_amplifier/attention'

class ConversationAttention:
    def __init__(self,log):
        self.log=log
        self.retry_after=0

    async def consider(self,request,client):
        if time.time()<self.retry_after:return False
        proposal=await request('/participation')
        if not proposal:return False
        capability=(client.info.get('_meta') or {}).get(META,{})
        supported=capability.get('version')==1 and capability.get('enabled') is True and capability.get('method')==METHOD
        try:
            if supported:
                offer=await client.request(METHOD,{'sessionId':client.session,'occurredAt':proposal['occurred_at'],'context':proposal['context']})
                if offer.get('action') not in ('engage','hold'):
                    raise RuntimeError('Invalid host attention response')
                if offer['action']=='engage' and not all(isinstance(offer.get(k),str) and offer[k] for k in ('id','ticket')):
                    raise RuntimeError('Missing host attention offer')
            else:
                # A plain ACP engine receives a bounded ordinary prompt and can remain silent.
                # This fallback has no pre-LLM decision-model savings.
                offer={'action':'engage','reason':'ordinary_acp_fallback'}
            payload={'signature':proposal['signature'],'action':offer['action']}
            if supported and offer['action']=='engage':payload['offer']={'id':offer['id'],'ticket':offer['ticket']}
            result=await request('/participation',payload)
            self.log('participation_offer_applied',action=offer['action'],reason=offer.get('reason'),event_id=offer.get('id'),source_current=True,queued=result.get('queued'),acp_admitted=False)
            return result.get('queued',False)
        except Exception as error:
            self.retry_after=time.time()+10
            self.log('participation_delivery_error',error_type=type(error).__name__)
            return False
