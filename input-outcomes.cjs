// Owner-only source delivery evidence. Never a work grant or completion verdict.
const CAPABILITY=Object.freeze({version:1,method:'GET',path:'/input-outcomes',max_ids:16});
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function requestIds(url){
 const q=new URL(url,'http://localhost').searchParams,values=q.getAll('ids');
 const ids=values.length===1?values[0].split(','):[];
 if([...q.keys()].some(k=>k!=='ids')||!ids.length||ids.length>16||new Set(ids).size!==ids.length||ids.some(id=>!uuid.test(id)))throw Error('Supply 1–16 distinct original queue UUIDs');
 return ids;
}
function base(id){return {request_id:id,delivery:'unknown',admitted_at:null,terminal_at:null,conversation_only:null,turn_task_id:null,blocked_reason:null,responses:[],task_authorizations:[],completion:'not_established'};}
function active(data){const t=data.turn;return (data.input_outcomes||[]).filter(r=>t?.request_ids?.includes(r.request_id)&&r.admitted_at===t.started_at&&r.delivery==='admitted');}
function admit(data){
 const t=data.turn;if(!t?.request_ids?.length)return;
 const records=data.input_outcomes||[];
 for(const id of t.request_ids){
  // An original input identity is not a replay slot. Never overwrite its proof.
  if(records.some(r=>r.request_id===id))continue;
  records.push({...base(id),delivery:'admitted',admitted_at:t.started_at,conversation_only:t.conversation_only===true,turn_task_id:t.task_id||null,source_ids:[...t.request_ids]});
 }
 const pinned=new Set(t.request_ids),retained=records.filter(r=>!pinned.has(r.request_id)).slice(-(500-pinned.size));
 data.input_outcomes=[...retained,...records.filter(r=>pinned.has(r.request_id))];
}
function blocked(data,reason){for(const r of active(data))r.blocked_reason=typeof reason==='string'?reason.slice(0,160):null;}
function response(data,event){
 if(event.kind!=='chat_sent')return;
 for(const r of active(data)){
  // A broad owner credential is not a Companion caller/audience binding.
  // Private text stays in the existing owner journal; never copy it here.
  if(event.whisper||event.provenance!=='minecraft_public_chat'){r.private_responses_withheld=true;continue;}
  const text=event.sent;
  if(typeof text!=='string'||text.length>240){r.responses_omitted=true;continue;}
  r.responses.push({id:event.id,at:event.time,text,audience:'public'});
  if(r.responses.length>32){r.responses.shift();r.responses_omitted=true;}
 }
}
function settle(data,{interrupted=false,reason=null,at=new Date().toISOString()}={}){
 for(const r of active(data)){r.delivery=interrupted?'interrupted':'terminal';r.terminal_at=at;if(reason)r.blocked_reason=reason;}
}
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
  return r;
 });
 return {version:1,observed_at:observedAt,outcomes};
}
module.exports={CAPABILITY,requestIds,admit,blocked,response,settle,query};
