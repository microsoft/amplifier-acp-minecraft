"""Source facts and admission delivery; shared social policy belongs to the ACP host."""
import hashlib
import json
import math
import time
from urllib.error import HTTPError

META='com.microsoft.amplifier.attention'
METHOD='_amplifier/attention'
REASONS=frozenset(('source_changed','invalid_action','non_public_evidence','inbox_full',
                   'disabled','peer_window_expired','peer_budget_exhausted','peer_budget_or_window'))
LEGACY_REASONS={
    'Conversation changed during participation assessment':'source_changed',
    'Invalid participation action':'invalid_action',
    'Participation evidence is not public game chat':'non_public_evidence',
    'Conversation inbox is full; retry after processing queued messages':'inbox_full',
    'Conversation attention is not enabled':'disabled',
    'Peer participation budget or human-activity window expired':'peer_budget_or_window',
}
# Diagnostic vocabulary only: the host still decides every engage/hold outcome.
HOST_REASONS=frozenset(('judgment','semantic_uncertainty','low_confidence','provider_refusal',
                       'provider_error','duplicate','stale','superseded','decision_budget',
                       'invalidated','ordinary_acp_fallback'))
OFFER_REASONS=frozenset(('invalid_host_response','missing_host_offer','expired_host_offer'))

def fingerprint(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:24]

class InvalidOffer(Exception):
    pass

def local_error_reason(error):
    """Read only bounded local error JSON; never log response text, URLs or headers."""
    try:
        raw=error.read(2049)
        if len(raw)>2048:return 'unknown'
        value=json.loads(raw)
        if not isinstance(value,dict):return 'unknown'
        code=value.get('code')
        if isinstance(code,str) and code in REASONS:return code
        text=value.get('error')
        return LEGACY_REASONS.get(text,'unknown') if isinstance(text,str) else 'unknown'
    except Exception:
        return 'unknown'
    finally:
        error.close()

class ConversationAttention:
    def __init__(self,log):
        self.log=log
        self.retry_after=0
        self.retry_key=None
        self.failures=0
        self.deferred=None

    async def consider(self,request,client):
        # Fetch fresh source facts while backing off a known proposal, so a new
        # human message is not delayed by a previous rejection. Failed source
        # fetches themselves back off until local transport can recover.
        if self.retry_key is None and time.time()<self.retry_after:return False
        stage='source_fetch';key=None;evaluation_requested=False
        try:
            proposal=await request('/participation')
            if not proposal:
                self.retry_key=None;self.failures=0;self.retry_after=0;self.deferred=None
                return False
            key=fingerprint(proposal['signature'])
            if key!=self.retry_key:
                self.retry_key=key;self.failures=0;self.retry_after=0
            delivery=proposal.get('delivery') or {}
            if delivery.get('eligible') is False:
                reason=delivery.get('reason_code')
                reason=reason if isinstance(reason,str) and reason in REASONS else 'unknown'
                if self.deferred!=(key,reason):
                    self.log('participation_delivery_deferred',stage='local_preflight',reason_code=reason,
                             proposal_fingerprint=key,evaluation_requested=False,acp_admitted=False)
                self.deferred=(key,reason);self.retry_after=0;self.failures=0
                return False
            self.deferred=None
            if time.time()<self.retry_after:return False
            capability=(client.info.get('_meta') or {}).get(META,{})
            supported=capability.get('version')==1 and capability.get('enabled') is True and capability.get('method')==METHOD
            if supported:
                stage='host_evaluation';evaluation_requested=True
                offer=await client.request(METHOD,{'sessionId':client.session,'occurredAt':proposal['occurred_at'],'context':proposal['context']})
                stage='offer_validation'
                if not isinstance(offer,dict) or offer.get('action') not in ('engage','hold'):
                    raise InvalidOffer('invalid_host_response')
                if offer['action']=='engage' and not all(isinstance(offer.get(k),str) and offer[k] for k in ('id','ticket')):
                    raise InvalidOffer('missing_host_offer')
                if offer['action']=='engage' and 'expiresAt' in offer:
                    expiry=offer['expiresAt']
                    if type(expiry) not in (int,float) or not math.isfinite(expiry):
                        raise InvalidOffer('invalid_host_response')
                    if expiry<=time.time()*1000:raise InvalidOffer('expired_host_offer')
            else:
                # A plain ACP engine receives a bounded ordinary prompt and can remain silent.
                # This fallback has no pre-LLM decision-model savings.
                offer={'action':'engage','reason':'ordinary_acp_fallback'}
            payload={'signature':proposal['signature'],'action':offer['action']}
            if supported and offer['action']=='engage':payload['offer']={'id':offer['id'],'ticket':offer['ticket']}
            stage='local_delivery'
            result=await request('/participation',payload)
            if not isinstance(result,dict) or result.get('queued') is not (offer['action']=='engage'):
                # A malformed/lost reply is not proof of acceptance or rejection.
                raise ValueError('Invalid delivery receipt')
            self.retry_after=0;self.failures=0
            reason=offer.get('reason')
            self.log('participation_offer_applied',action=offer['action'],
                     reason=reason if isinstance(reason,str) and reason in HOST_REASONS else 'unknown',
                     event_fingerprint=fingerprint(offer['id']) if isinstance(offer.get('id'),str) else None,
                     source_current=True,queued=result['queued'],acp_admitted=False)
            return result['queued']
        except Exception as error:
            if key!=self.retry_key:self.failures=0
            self.retry_key=key;self.failures=min(self.failures+1,5)
            delay=min(120,10*2**(self.failures-1));self.retry_after=time.time()+delay
            status=error.code if isinstance(error,HTTPError) and type(error.code) is int and 100<=error.code<=599 else None
            reason=local_error_reason(error) if isinstance(error,HTTPError) and stage in ('source_fetch','local_delivery') else 'unknown'
            if isinstance(error,InvalidOffer) and stage=='offer_validation':
                code=error.args[0] if error.args else None
                reason=code if isinstance(code,str) and code in OFFER_REASONS else 'unknown'
            outcome='not_attempted'
            if stage=='local_delivery':
                outcome='rejected' if reason in REASONS and status is not None and 400<=status<500 else 'unknown'
            # Never cache a POST/offer. Next attempt reads the body's pending
            # source again; its atomic pending-ID check prevents replay even if
            # a previous HTTP request commits late or its reply was lost.
            error_type=next((kind.__name__ for kind in (HTTPError,TimeoutError,ConnectionError,InvalidOffer,ValueError,RuntimeError)
                             if isinstance(error,kind)),'other')
            self.log('participation_delivery_error',stage=stage,error_type=error_type,
                     http_status=status,reason_code=reason,proposal_fingerprint=key,
                     retry_after_seconds=delay,evaluation_requested=evaluation_requested,
                     delivery_outcome=outcome,queued=None if outcome=='unknown' else False,acp_admitted=False)
            return False
