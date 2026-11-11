// Authenticated owner review of retained, terminal movement failures. This does
// not classify effects automatically, retry a move or resume an old assignment.
const crypto=require('node:crypto');
const digest=value=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
const hash=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const uuid=value=>typeof value==='string'&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value);
function exact(value,keys){if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).sort().join()!==keys.sort().join())throw Error('Malformed activity review');}
function review(history,cfg,input,observation){
 exact(input,['generation','request_id','expected_turn_sha256','expected_position','expected_inventory_sha256','evidence_sha256','reviews']);
 exact(input.expected_position,['x','y','z']);
 if(!Number.isSafeInteger(input.generation)||!uuid(input.request_id)||!hash(input.expected_turn_sha256)||!hash(input.expected_inventory_sha256)||!hash(input.evidence_sha256)||!Object.values(input.expected_position).every(Number.isFinite)||!Array.isArray(input.reviews)||input.reviews.length<1||input.reviews.length>64)throw Error('Malformed activity review');
 for(const item of input.reviews){
  exact(item,['action_id','receipt_sha256','outcome','reason']);
  if(typeof item.action_id!=='string'||!hash(item.receipt_sha256)||!['no_effect','settled_failed_movement'].includes(item.outcome)||typeof item.reason!=='string'||!item.reason.trim()||item.reason.length>2000)throw Error('Each failed movement needs concrete reviewed evidence');
 }
 const policy=require('./activity-policy.cjs'),turn=history.data.last_turn;
 if(!policy.enabled(cfg)||history.data.turn||!turn?.activity||turn.task_id!==null||turn.interrupted||!Array.isArray(turn.actions))throw Error('Exact idle non-interrupted activity required');
 if(['x','y','z'].some(k=>input.expected_position[k]!==observation.position?.[k])||digest(observation.inventory)!==input.expected_inventory_sha256)throw Error('Current position or inventory changed');
 const requestHash=digest(input),prior=turn.effect_review;
 if(prior){
  if(prior.request_sha256!==requestHash)throw Error('Activity already reviewed or request changed');
  return {...prior.result,duplicate:true,activity_allowed:policy.allowed(history,cfg),blocked_reason:policy.reason(history,cfg)};
 }
 if(digest(turn)!==input.expected_turn_sha256)throw Error('Activity turn changed');
 const uncertain=turn.actions.filter(a=>a.status==='uncertain');
 if(!uncertain.length||turn.actions.some(a=>!['succeeded','uncertain'].includes(a.status)||a.review)||new Set(turn.actions.map(a=>a.id)).size!==turn.actions.length||new Set(input.reviews.map(a=>a.action_id)).size!==input.reviews.length||input.reviews.length!==uncertain.length||uncertain.some(a=>!input.reviews.some(r=>r.action_id===a.id)))throw Error('Review must cover every uncertain action exactly, with no pending effects');
 for(const item of input.reviews){
  const events=history.data.events.filter(e=>e.action_id===item.action_id);
  const starts=events.filter(e=>e.kind==='action_started'),ends=events.filter(e=>['action_result','action_failed'].includes(e.kind));
  const start=starts[0],end=ends[0];
  if(starts.length!==1||ends.length!==1||start.action!=='move'||end.action!=='move'||end.kind!=='action_failed'||end.timeout||end.operation_settled===false||!Number.isFinite(Date.parse(start.time))||!Number.isFinite(Date.parse(end.time))||!(Date.parse(start.time)>=Date.parse(turn.started_at))||Date.parse(end.time)<Date.parse(start.time)||digest(start.arguments)!==digest(end.arguments)||digest(end)!==item.receipt_sha256)throw Error('Exact retained terminal movement receipt required');
  if(item.outcome==='no_effect'&&start.arguments?.mode!=='walk_only')throw Error('Normal movement must retain its settled failed-effects distinction');
 }
 const candidate=structuredClone(turn),at=new Date().toISOString();
 for(const item of input.reviews)candidate.actions.find(a=>a.id===item.action_id).review={...item,reviewed_at:at,original_turn_sha256:input.expected_turn_sha256,evidence_sha256:input.evidence_sha256};
 const result={request_id:input.request_id,reviewed_at:at,action_ids:input.reviews.map(r=>r.action_id),task_changed:false,replayed:false,future_work_only:true};
 candidate.effect_review={request_id:input.request_id,request_sha256:requestHash,original_turn_sha256:input.expected_turn_sha256,evidence_sha256:input.evidence_sha256,observation:structuredClone(observation),future_work_only:true,result};
 history.data.last_turn=candidate;
 try{history.save();}catch(error){history.data.last_turn=turn;throw error;}
 return {...result,activity_allowed:policy.allowed(history,cfg),blocked_reason:policy.reason(history,cfg)};
}
module.exports={review};
