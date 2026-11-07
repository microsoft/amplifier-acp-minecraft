"""Settle domain operations after a prompt; never create another model request."""
import asyncio,time

async def settle_sequence(request,result,observe,*,sleep=asyncio.sleep,clock=time.monotonic):
    status=await request('/status')
    if not status.get('action_sequence'):
        return {'waited':False}
    operation_id=status['action_sequence']['id'];last_renewed=clock();cancel_at=None
    if result.get('stop_reason')!='end_turn' or result.get('unsettled_tools'):
        await request('/sequence/cancel',{});cancel_at=clock()
    observe('sequence_settlement_started',operation_id=operation_id,model_prompt_terminal=True)
    while status.get('action_sequence'):
        if status['action_sequence']['id']!=operation_id:
            raise RuntimeError('Domain operation changed during settlement')
        if not status.get('turn_active') and cancel_at is None:
            await request('/sequence/cancel',{});cancel_at=clock()
        if cancel_at is not None and clock()-cancel_at>65:
            raise RuntimeError('Cancelled operation still unsettled; inspect effects without replay')
        lease=status.get('action_lease') or {}
        if cancel_at is None and lease.get('renewable') and clock()-last_renewed>=30:
            await request('/turn/renew',{'lease_id':lease['lease_id'],'task_id':lease['task_id']});last_renewed=clock()
        await sleep(.25);status=await request('/status')
    observe('sequence_settlement_observed',operation_id=operation_id,busy=status.get('busy'),completion_claim=False)
    return {'waited':True,'operation_id':operation_id}
