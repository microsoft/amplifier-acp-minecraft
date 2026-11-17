// Owner-only settlement review. Keep the interrupted turn intact; no action,
// input or old continuation is retried, and no task authority is amended.
const crypto=require('node:crypto');
const digest=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex');
const hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const point=v=>v&&['x','y','z'].every(k=>Number.isFinite(v[k]));
const samePoint=(a,b)=>point(a)&&point(b)&&['x','y','z'].every(k=>a[k]===b[k]);
function exact(v,keys){if(!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).sort().join()!==keys.sort().join())throw Error('Malformed interrupted activity review');}
function reviewed(turn){
 const r=turn?.effect_review;
 if(r?.scope!=='interrupted_activity'||r.future_work_only!==true||!hash(r.original_turn_sha256))return false;
 const original={...turn};delete original.effect_review;
 return digest(original)===r.original_turn_sha256;
}
function terminal(turn,action,start,end){
 const r=end.result,a=start.arguments;
 if(end.timeout||end.operation_settled===false||r?.timeout||r?.operation_settled===false)throw Error('Unsettled or timed-out actions cannot be reviewed here');
 if(action.status==='failed_settled'){
  const f=end.settled_failure;
  if(start.action!=='move'||end.kind!=='action_failed'||f?.kind!=='settled_failed_movement'||f.reached!==false||f.replayed!==false||!point(f.before)||!point(f.position)||digest(f)!==digest(action.outcome)||typeof end.error!=='string'||/cancel|interrupt|transport|timed?\s*out|timeout|unknown/i.test(end.error))throw Error('Affirmative settled movement failure required');
  return;
 }
 if(end.kind!=='action_result'||!r||r.error||r.settled_failure)throw Error('Successful terminal receipt required');
 if(start.action==='move'){
  if(r.reached!==true||!point(r.position)||!samePoint(r.target,a))throw Error('Movement arrival receipt required');
 }else if(start.action==='place'){
  if(r.verified!==true||!samePoint(r.position,a)||typeof a.item!=='string'||r.actual!==a.item)throw Error('Exact server-verified single placement required');
 }else if(['chat','tell'].includes(start.action)){
  const matches=(turn.speech_operations||[]).filter(o=>o.id===r.operation_id),o=matches[0];
  if(matches.length!==1||o.status!=='submitted'||r.transport_submitted!==true||!Array.isArray(o.packets)||!o.packets.length||o.packets.length!==r.packet_count||o.packets.some(p=>p.status!=='submitted'||typeof p.text!=='string'||p.receipt?.sent!==p.text)||o.packets.map(p=>p.text).join(' ')!==r.sent||digest(o.result)!==digest(r))throw Error('Every speech packet needs its retained submission receipt');
  // Transport submission remains distinct from receipt by another player.
 }else throw Error('This action has no supported synchronous settlement review');
}
// This is authenticated owner review of retained external evidence, not a
// classification inferred from an empty body action list or a tool label.
function deniedPrompt(history,turn,denial,observation){
 exact(denial,['version','session','turn_started_at','prompt_id','complete_tool_ledger','calls','terminal','sources']);
 exact(denial.session,['session','binding']);
 exact(denial.terminal,['stop_reason','unsettled_tool_count']);
 exact(denial.sources,['client_sha256','instance_sha256','engine_sha256']);
 const id=v=>typeof v==='string'&&v.length>0&&v.length<=256;
 if(denial.version!==1||!id(denial.session.session)||!hash(denial.session.binding)||
    denial.session.session!==observation.session?.session||denial.session.binding!==observation.session?.binding||
    denial.turn_started_at!==turn.started_at||!id(denial.prompt_id)||denial.complete_tool_ledger!==true||
    denial.terminal.stop_reason!=='cancelled'||denial.terminal.unsettled_tool_count!==0||
    !Object.values(denial.sources).every(hash))throw Error('Exact complete original denied prompt evidence required');
 if(!Array.isArray(denial.calls)||!denial.calls.length||denial.calls.length>64||
    new Set(denial.calls.map(c=>c?.id)).size!==denial.calls.length)throw Error('Every original call needs distinct pre-dispatch denial evidence');
 for(const call of denial.calls){
  exact(call,['id','permission','reason','status','dispatch']);
  if(!id(call.id)||call.permission!=='cancelled'||call.reason!=='unverified_tool_identity'||
     call.status!=='failed'||call.dispatch!=='not_dispatched')throw Error('Missing or ambiguous dispatch remains held');
 }
 if(turn.actions.length!==0||!Array.isArray(turn.request_ids)||turn.request_ids.length||
    ('speech_operations' in turn&&(!Array.isArray(turn.speech_operations)||turn.speech_operations.length))||
    'activity_report' in turn||observation.inventory?.cursor!==null)throw Error('Only empty denied activity without input or speech effects is reviewable');
 const start=Date.parse(turn.started_at);
 if(!Number.isFinite(start)||history.data.events.some(e=>['action_started','action_result','action_failed'].includes(e.kind)&&
    (!Number.isFinite(Date.parse(e.time))||Date.parse(e.time)>=start)))throw Error('Domain action evidence cannot be cleared by permission denial');
}
function review(history,cfg,input,observation){
 const denial=Object.hasOwn(input,'permission_denial');
 exact(input,['generation','request_id','expected_turn_sha256','expected_task_sha256','expected_position','expected_inventory_sha256','evidence_sha256','reason','receipts',...(denial?['permission_denial']:[])]);
 exact(input.expected_position,['x','y','z']);
 if(!Number.isSafeInteger(input.generation)||typeof input.request_id!=='string'||!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(input.request_id)||!['expected_turn_sha256','expected_task_sha256','expected_inventory_sha256','evidence_sha256'].every(k=>hash(input[k]))||!point(input.expected_position)||typeof input.reason!=='string'||!input.reason.trim()||input.reason.length>2000||!Array.isArray(input.receipts)||(denial?input.receipts.length!==0:!input.receipts.length)||input.receipts.length>64)throw Error('Exact interrupted activity evidence required');
 for(const r of input.receipts){exact(r,['action_id','receipt_sha256']);if(typeof r.action_id!=='string'||!r.action_id||!hash(r.receipt_sha256))throw Error('Exact action receipt required');}
 const policy=require('./activity-policy.cjs'),turn=history.data.last_turn;
 if(!policy.enabled(cfg)||history.data.activity_stop||history.data.turn||!turn?.activity||turn.task_id!==null||turn.interrupted!==true||!Array.isArray(turn.actions))throw Error('Exact idle interrupted ordinary activity required; Stop remains binding');
 if(!samePoint(input.expected_position,observation.position)||digest(observation.inventory)!==input.expected_inventory_sha256||observation.inventory?.cursor)throw Error('Current position/inventory changed or cursor unresolved');
 if(digest(history.data.task??null)!==input.expected_task_sha256)throw Error('Current task changed');
 if(denial)deniedPrompt(history,turn,input.permission_denial,observation);
 const requestHash=digest(input),prior=turn.effect_review;
 if(prior){
  if(prior.request_sha256!==requestHash||!reviewed(turn))throw Error('Activity already reviewed or evidence changed');
  return {...prior.result,duplicate:true,activity_allowed:policy.allowed(history,cfg),blocked_reason:policy.reason(history,cfg)};
 }
 if(digest(turn)!==input.expected_turn_sha256)throw Error('Interrupted activity changed');
 if(turn.actions.length!==input.receipts.length||turn.actions.some(a=>!['succeeded','failed_settled'].includes(a.status)||a.review)||new Set(turn.actions.map(a=>a.id)).size!==turn.actions.length||new Set(input.receipts.map(r=>r.action_id)).size!==input.receipts.length||turn.actions.some(a=>!input.receipts.some(r=>r.action_id===a.id)))throw Error('Review must cover all and only settled actions');
 if((turn.speech_operations||[]).some(o=>o.status!=='submitted'))throw Error('Unresolved speech submission remains');
 let previous=Date.parse(turn.started_at);
 if(!Number.isFinite(previous))throw Error('Original activity time required');
 // Sequence acceptance and a stopped process are not terminal operation proof.
 // This review is deliberately limited to direct synchronous actions.
 if((history.data.action_sequences||[]).some(s=>['running','interrupted'].includes(s.status)||!Number.isFinite(Date.parse(s.started_at))||Date.parse(s.started_at)>=previous))throw Error('Sequence history requires separate settlement review');
 for(const action of turn.actions){
  const events=history.data.events.filter(e=>e.action_id===action.id),starts=events.filter(e=>e.kind==='action_started'),ends=events.filter(e=>['action_result','action_failed'].includes(e.kind)),start=starts[0],end=ends[0];
  if(starts.length!==1||ends.length!==1||start.action!==end.action||digest(start.arguments)!==digest(end.arguments)||!Number.isFinite(Date.parse(start.time))||!Number.isFinite(Date.parse(end.time))||Date.parse(start.time)<previous||Date.parse(end.time)<Date.parse(start.time)||digest(end)!==input.receipts.find(r=>r.action_id===action.id).receipt_sha256)throw Error('Exact ordered start and terminal receipts required');
  terminal(turn,action,start,end);previous=Date.parse(end.time);
 }
 const candidate=structuredClone(turn),at=new Date().toISOString();
 const result={request_id:input.request_id,reviewed_at:at,action_ids:turn.actions.map(a=>a.id),task_changed:false,replayed:false,future_work_only:true};
 candidate.effect_review={scope:'interrupted_activity',future_work_only:true,request_sha256:requestHash,original_turn_sha256:input.expected_turn_sha256,expected_task_sha256:input.expected_task_sha256,evidence_sha256:input.evidence_sha256,reason:input.reason,receipts:structuredClone(input.receipts),...(denial?{permission_denial:structuredClone(input.permission_denial)}:{}),observation:structuredClone(observation),result};
 history.data.last_turn=candidate;
 try{history.save();}catch(error){history.data.last_turn=turn;throw error;}
 return {...result,activity_allowed:policy.allowed(history,cfg),blocked_reason:policy.reason(history,cfg)};
}
module.exports={review,reviewed};
