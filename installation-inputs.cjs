// Optional installation-owned ingress. Caller credentials are not game identities.
const crypto=require('node:crypto');
const outcomes=require('./input-outcomes.cjs');
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const equal=(a,b)=>typeof a==='string'&&typeof b==='string'&&Buffer.byteLength(a)===Buffer.byteLength(b)&&crypto.timingSafeEqual(Buffer.from(a),Buffer.from(b));
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const digest=v=>crypto.createHash('sha256').update(JSON.stringify(canonical(v))).digest('hex');
const capability=Object.freeze({version:1,submission:{method:'POST',path:'/task'},outcomes:{method:'POST',path:'/source-outcomes',max_items:16},source_identity:'credential_bound_caller_and_exact_source',idempotency:'same_caller_source_request_id_and_payload',private_game_responses:false,source_replies:{version:1,max_items:32,max_text_bytes:12000}});
function object(v,keys){if(!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).some(k=>!keys.includes(k))||keys.some(k=>!(k in v)))throw Error('Exact source fields required');}
function text(v,max){if(typeof v!=='string'||!v.trim()||v.length>max||/[\u0000-\u001f]/.test(v))throw Error('Invalid bounded source field');}
function source(v){
 object(v,['version','request_id','call_id','intent_id','revision','occurred_at','actor','audience']);
 if(v.version!==1||!uuid.test(v.request_id))throw Error('Unsupported source version or request identity');
 for(const k of ['call_id','intent_id','revision'])text(v[k],160);
 if(typeof v.occurred_at!=='string'||v.occurred_at.length>32||!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$/.test(v.occurred_at)||!Number.isFinite(Date.parse(v.occurred_at)))throw Error('Original UTC source time required');
 object(v.actor,['id','label']);text(v.actor.id,160);text(v.actor.label,160);
 object(v.audience,['kind','experience','id']);if(v.audience.kind!=='private')throw Error('Installation source audience must be private');text(v.audience.experience,80);text(v.audience.id,160);
 return v;
}
function callers(cfg){
 const list=cfg.installation_callers??[];
 if(!Array.isArray(list)||list.length>16)throw Error('Invalid installation caller enrollment');
 const ids=new Set(),secrets=new Set([cfg.token,cfg.context_token,cfg.presence_token].filter(Boolean));
 for(const c of list){object(c,['id','label','token']);text(c.id,80);text(c.label,160);if(!/^[a-zA-Z0-9_.-]+$/.test(c.id)||typeof c.token!=='string'||!/^[A-Za-z0-9_-]{32,256}$/.test(c.token)||ids.has(c.id)||secrets.has(c.token))throw Error('Caller identity and dedicated secret must be unique');ids.add(c.id);secrets.add(c.token);}
 return list;
}
function authenticate(list,authorization){return list.find(c=>equal(authorization,`Bearer ${c.token}`))||null;}
function allowed(method,url){return method==='GET'&&url==='/source-capabilities'||method==='POST'&&['/task','/source-outcomes'].includes(url);}
function enqueue(history,caller,payload,{now=Date.now(),seq=0}={}){
 object(payload,['text','source']);source(payload.source);
 if(typeof payload.text!=='string'||!payload.text.trim()||payload.text.length>12000)throw Error('Input must contain 1–12000 characters');
 const data=history.data,key=digest([caller.id,payload.source.request_id]),hash=digest(payload),old=data.installation_input_receipts?.[key];
 if(old){if(old.payload_hash!==hash)throw Error('Source request identity already has a different payload');return {receipt:{...old.receipt,duplicate:true},event:null};}
 const at=Date.parse(payload.source.occurred_at);
 if(at>now+5000||at<=now-600000||at<=(data.task_source_cutoff||0))throw Error('Original source is expired, future, or revoked');
 if((data.inbox||[]).length>=8)throw Error('Input queue is full');
 const received=new Date(now).toISOString(),id=crypto.randomUUID();
 const attribution={caller:{id:caller.id,label:caller.label},...structuredClone(payload.source)};
 const event={id,seq,time:payload.source.occurred_at,received_at:received,kind:'chat',username:caller.label,message:payload.text,source:'human',accepted:true,whisper:false,provenance:'operator_control',transport:{kind:'authenticated_operator_control',caller_id:caller.id},installation_source:attribution,reviewers:[]};
 const receipt={queued:true,request_id:id,source_request_id:payload.source.request_id,received_at:received,duplicate:false};
 const priorReceipts=data.installation_input_receipts,priorInbox=data.inbox,priorEvents=data.events;
 const inbox=data.inbox||(data.inbox=[]),events=data.events||(data.events=[]),ni=inbox.length,ne=events.length;
 data.installation_input_receipts={...(priorReceipts||{}),[key]:{payload_hash:hash,source:attribution,receipt}};
 inbox.push({id,username:caller.label,message:payload.text,source:'human'});events.push(event);
 try{history.save();}catch(error){inbox.length=ni;events.length=ne;data.inbox=priorInbox;data.events=priorEvents;if(priorReceipts===undefined)delete data.installation_input_receipts;else data.installation_input_receipts=priorReceipts;throw error;}
 return {receipt,event};
}
// The durable ingress receipt, not a caller label or model field, binds replies.
function replyRoute(data,ids){
 const records=ids.map(id=>Object.values(data.installation_input_receipts||{}).find(r=>r.receipt.request_id===id)||null);
 if(!records.some(Boolean)){
  if(ids.some(id=>data.events?.find(e=>e.id===id)?.installation_source))throw Error('Private source binding is not retained');
  return null;
 }
 if(ids.length!==1||!records[0])throw Error('Private source replies require their own admission');
 return {kind:'installation',request_id:ids[0],source:structuredClone(records[0].source)};
}
function projectInput(data,message){
 const route=replyRoute(data,[message.id]);
 return route?{...message,reply_scope:'installation:'+route.request_id,installation_source:route.source}:message;
}
function replyRecord(data,route){
 if(route?.kind!=='installation')throw Error('No installation reply route');
 const record=data.installation_input_receipts?.[digest([route.source?.caller?.id,route.source?.request_id])];
 if(!record||record.receipt.request_id!==route.request_id||digest(record.source)!==digest(route.source))throw Error('Private reply source binding changed');
 return record;
}
function saveReply(history,text){
 const turn=history.data.turn,route=turn?.reply_route,record=replyRecord(history.data,route);
 if(typeof text!=='string'||!text.trim()||Buffer.byteLength(text)>capability.source_replies.max_text_bytes)throw Error('Private reply exceeds its bounded text limit');
 const id=digest([route.request_id,turn.started_at,text]),previous=(record.source_replies||[]).find(r=>r.id===id);
 if(previous)return {...structuredClone(previous),duplicate:true};
 if((record.source_replies||[]).length>=capability.source_replies.max_items){
  const omitted=record.source_replies_omitted;record.source_replies_omitted=true;
  try{history.save();}catch(error){if(omitted===undefined)delete record.source_replies_omitted;else record.source_replies_omitted=omitted;throw error;}
  throw Error('Private reply capacity reached; inspect retained source outcomes');
 }
 const item={id,at:new Date().toISOString(),text,audience:structuredClone(record.source.audience),delivery:'recorded'};
 const old=record.source_replies;record.source_replies=[...(old||[]),item];
 try{history.save();}catch(error){if(old===undefined)delete record.source_replies;else record.source_replies=old;throw error;}
 return structuredClone(item);
}
function query(history,caller,payload,{now=Date.now()}={}){
 object(payload,['version','requests']);if(payload.version!==1||!Array.isArray(payload.requests)||!payload.requests.length||payload.requests.length>16)throw Error('Supply 1–16 exact source outcome requests');
 const keys=new Set();
 const rows=payload.requests.map(q=>{
  object(q,['request_id','source']);if(!uuid.test(q.request_id)||keys.has(q.request_id))throw Error('Distinct queue UUIDs required');keys.add(q.request_id);source(q.source);
  const r=history.data.installation_input_receipts?.[digest([caller.id,q.source.request_id])];
  const unknown={request_id:q.request_id,delivery:'unknown',reason:'not_retained_or_not_authorized',completion:'not_established'};
  if(!r||r.receipt.request_id!==q.request_id||digest({...q.source,caller:r.source.caller})!==digest(r.source))return unknown;
  const value=outcomes.query(history.data,[q.request_id],new Date(now).toISOString()).outcomes[0];
  const count=value.source_ids?.length||0;delete value.source_ids;
  return {...value,source:structuredClone(r.source),response_association:count>1?'shared_turn':count===1?'single_source':'not_established',private_game_responses_included:false,source_replies:structuredClone(r.source_replies||[]),...(r.source_replies_omitted?{source_replies_omitted:true}:{})};
 });
 return {version:1,observed_at:new Date(now).toISOString(),outcomes:rows};
}
module.exports={projectInput,replyRoute,replyRecord,saveReply,capability,callers,authenticate,allowed,enqueue,query,source};
