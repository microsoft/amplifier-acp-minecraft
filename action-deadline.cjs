// Bound an experience action, then give cancellation a short chance to settle.
// A timeout never means success, even if the worker finishes during cleanup.
async function boundedAction(work,{timeoutMs=60000,settleMs=1000,cancel,onUnsettled}){
 let timer,drainTimer,timedOut=false,settled=false,cancellationFailed=false;
 const operation=Promise.resolve().then(work);
 const completion=operation.then(()=>{settled=true;},()=>{settled=true;});
 try{
  return await Promise.race([operation,new Promise((_,reject)=>{
   timer=setTimeout(()=>{timedOut=true;try{cancel();}catch{cancellationFailed=true;}finally{reject(Error('Action timed out'));}},timeoutMs);
  })]);
 }catch(error){
  if(!timedOut)throw error;
  await Promise.race([completion,new Promise(resolve=>{drainTimer=setTimeout(resolve,settleMs);})]);
  if(!settled||cancellationFailed)onUnsettled(completion);
  const failure=Error(settled&&!cancellationFailed?
   'Action timed out; movement stopped. Inspect current observations before choosing a different approach.':
   'Action timed out; cancellation has not settled. This turn is closed and further actions must wait for review.');
  failure.actionTimeout=true;failure.operationSettled=settled;
  throw failure;
 }finally{clearTimeout(timer);clearTimeout(drainTimer);}
}
module.exports={boundedAction};
