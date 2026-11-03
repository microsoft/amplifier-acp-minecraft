const test=require('node:test'),assert=require('node:assert/strict');
const {boundedAction}=require('../action-deadline.cjs');
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
test('ordinary success and failure never invoke cancellation',async()=>{
 const options={timeoutMs:100,cancel(){assert.fail('Unexpected cancellation');},onUnsettled(){assert.fail('Unexpected unsettled worker');}};
 assert.equal(await boundedAction(async()=>42,options),42);
 const original=Error('No path');await assert.rejects(boundedAction(async()=>{throw original;},options),e=>e===original);
});
test('timeout waits for cancellation cleanup and never reports late success',async()=>{
 let release,cleaned=false,cancelled=0;
 const worker=new Promise(resolve=>{release=resolve;}).then(async()=>{await wait(15);cleaned=true;return 'late success';});
 await assert.rejects(boundedAction(()=>worker,{timeoutMs:5,settleMs:100,
  cancel(){cancelled++;release();},onUnsettled(){assert.fail('Worker did settle');}}),
  e=>e.actionTimeout&&e.operationSettled&&cleaned);
 assert.equal(cancelled,1);
});
test('an unresponsive worker stays visible until its eventual cleanup',async()=>{
 let release,pending,closed=false;
 const worker=new Promise(resolve=>{release=resolve;});
 await assert.rejects(boundedAction(()=>worker,{timeoutMs:5,settleMs:5,cancel(){},
  onUnsettled(p){closed=true;pending=p;}}),e=>e.actionTimeout&&!e.operationSettled&&closed);
 let drained=false;pending.then(()=>{drained=true;});await wait(5);assert.equal(drained,false);
 release();await pending;assert.equal(drained,true);
});
test('a cancellation failure is contained and invokes the closed-turn fallback',async()=>{
 let release,closed=false;
 const worker=new Promise(resolve=>{release=resolve;});
 await assert.rejects(boundedAction(()=>worker,{timeoutMs:5,settleMs:5,cancel(){throw Error('Cancellation failed');},
  onUnsettled(){closed=true;}}),e=>e.actionTimeout&&!e.operationSettled&&closed);
 release();
});
