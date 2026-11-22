// Owner-only source delivery evidence. Never a work grant or completion verdict.
const CAPABILITY=Object.freeze({version:1,method:'GET',path:'/input-outcomes',max_ids:16});
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function requestIds(url){
 const q=new URL(url,'http://localhost').searchParams,values=q.getAll('ids');
 const ids=values.length===1?values[0].split(','):[];
 if([...q.keys()].some(k=>k!=='ids')||!ids.length||ids.length>16||new Set(ids).size!==ids.length||ids.some(id=>!uuid.test(id)))throw Error('Supply 1–16 distinct original queue UUIDs');
 return ids;
}
function base(id){return {request_id:id,delivery:'unknown',admitted_at:null,terminal_at:null,conversation_only:null,turn_task_id:null,blocked_reason:null,responses:[],task_authorizations:[],work_resumptions:[],completion:'not_established'};}
function query(data,ids,observedAt=new Date().toISOString()){
 const outcomes=ids.map(id=>{
  const retained=(data.input_outcomes||[]).find(r=>r.request_id===id);
  let r=retained?structuredClone(retained):{...base(id),reason:'not_retained'};
  if(!retained){
   const turn=[data.turn,data.last_turn,data.last_conversation_turn].find(t=>t?.request_ids?.includes(id));
   const admission=(data.conversation_admissions||[]).find(a=>a.ids.includes(id));
   if(turn||admission)r={...r,delivery:'admitted',admitted_at:turn?.started_at||new Date(admission.at).toISOString(),conversation_only:turn?turn.conversation_only===true:true,turn_task_id:turn?.task_id||null,source_ids:[...(turn?.request_ids||admission.ids)],reason:'terminal_not_retained'};
   else if((data.inbox||[]).some(m=>m.id===id))r={...r,delivery:'queued',reason:undefined};
  }
  r.task_authorizations=(data.task_authorizations||[]).filter(a=>a.source?.id===id&&['accept','amend'].includes(a.operation)).map(a=>({operation:a.operation,task_id:a.result.task_id,authority_revision:a.result.authority_revision})).slice(-16);
  // Scheduling is a separate saved result, not a new admission or proof of work.
  // Do not copy private source text or derive a result from today's task state.
  const resumptions=(data.work_resumptions||[]).filter(a=>a.request_id===id&&a.source?.id===id);
  const valid=resumptions.filter(a=>typeof a.task_id==='string'&&a.result?.task_id===a.task_id&&typeof a.result.status==='string'&&typeof a.result.scheduled==='boolean'&&typeof a.result.execution_started==='boolean');
  r.work_resumptions=valid.slice(-16).map(a=>({task_id:a.task_id,recorded_status:a.result.status,scheduled:a.result.scheduled,execution_started:a.result.execution_started}));
  if(valid.length>16||valid.length!==resumptions.length)r.work_resumptions_omitted=true;
  return r;
 });
 return {version:1,observed_at:observedAt,outcomes};
}
module.exports={CAPABILITY,requestIds,query};
