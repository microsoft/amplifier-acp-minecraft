// Local world-execution authority. Social attention and ACP remain independent.
const {createHash,randomUUID}=require('node:crypto');
const {ConversationAdmission}=require('./conversation-admission.cjs');
const INTAKE_TOOLS=new Set(['task_accept','task_amend']);
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const digest=value=>createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
class TaskIntake {
 constructor(history,cfg,{now=Date.now}={}){this.history=history;this.cfg=cfg;this.now=now;}
 enabled(){return this.cfg.human_task_intake?.enabled===true;}
 limits(){
  const p=this.cfg.human_task_intake||{},turns=this.cfg.task_max_turns||12,seconds=this.cfg.task_max_seconds||2400;
  const limits={default_turns:turns,default_seconds:seconds,max_turns:p.max_turns??turns,max_seconds:p.max_seconds??seconds};
  if(!Object.values(limits).every(v=>Number.isSafeInteger(v)&&v>0)||limits.max_turns<turns||limits.max_seconds<seconds||limits.max_turns>10000||limits.max_seconds>604800)throw Error('Invalid human task defaults/ceilings; inspect installation policy');
  return limits;
 }
 requiresReview(task){
  if(task?.status==='needs_review')return true;
  const turn=this.history.data.last_turn;
  if(!task||turn?.task_id!==task.id||!turn.interrupted)return false;
  // Deadline expiry must not erase the unresolved interruption. Only the
  // existing explicit/settled-receipt review path can clear that evidence.
  return !(task.progress||[]).some(p=>['operator_recovery','receipt_reconciliation'].includes(p.kind)&&Date.parse(p.at)>=Date.parse(turn.started_at));
 }
 runnable(){const t=this.history.task();return !!(this.enabled()&&t?.authority?.kind==='human_game_request'&&['running','waiting'].includes(t.status)&&t.deadline>this.now()&&(t.turns<t.max_turns||(this.history.data.turn?.task_id===t.id&&t.turns===t.max_turns)));}
 capabilities(){
  const enabled=this.enabled();let limits=null,policy_error=null;try{limits=this.limits();}catch(e){policy_error=e.message;}
  const configured_chat_only=this.cfg.incoming_chat_only===true,conversation_only=this.history.data.turn?.conversation_only===true,task=this.history.task();
  const can_accept=enabled&&!policy_error&&!this.requiresReview(task)&&!['running','waiting','blocked','needs_review'].includes(task?.status);
  const can_amend=enabled&&!policy_error&&!this.requiresReview(task)&&task?.authority?.kind==='human_game_request'&&!['stopped','needs_review'].includes(task.status);
  const work_blocked_reason=this.requiresReview(task)?'unresolved_interruption':!enabled?(configured_chat_only?'installation_chat_only':null):!task?'no_accepted_assignment':task.authority?.kind!=='human_game_request'?'no_current_intake_authority':task.deadline<=this.now()?'assignment_expired':task.turns>=task.max_turns&&!this.runnable()?'assignment_turn_cap':['stopped','needs_review','blocked','review'].includes(task.status)?'assignment_'+task.status:null;
  return {version:1,mode:enabled?'human_requests':configured_chat_only?'chat_only':'legacy_work',
   configured_chat_only,conversation_only,task_intake_enabled:enabled&&!policy_error,
   can_accept,can_amend:!!can_amend,work_blocked_reason,
   can_delegate_execution:false,delegation_reason:'Peer messages and responsibility records do not grant this body execution authority.',
   autonomous_work_allowed:enabled?(!policy_error&&this.runnable()):!configured_chat_only,
   defaults:limits?{turns:limits.default_turns,seconds:limits.default_seconds}:null,
   ceilings:limits?{cumulative_turns:limits.max_turns,seconds_from_amendment:limits.max_seconds}:null,
   blocked_reason:policy_error?'invalid_task_policy':!enabled&&configured_chat_only?'installation_chat_only':conversation_only?'reply_turn_no_world_effects':null,
   task_revision:task?.authority_revision??0,
   assignment:task?{id:task.id,status:task.status,consumed_turns:task.turns,cumulative_cap:task.max_turns,deadline:task.deadline,remaining_turns:Math.max(0,task.max_turns-task.turns),remaining_ms:Math.max(0,task.deadline-this.now())}:null,
   capacity:{autonomous_turns_per_hour:30,reply_turns_per_hour:new ConversationAdmission(this.history,this.cfg).limit(),provider_remaining:null,provider_limits:'Enforced independently by the connected host/provider; remaining capacity is not known to this body.'},
   reviewed_requests:(this.history.data.reviewed_task_sources||[]).filter(x=>x.valid_until>this.now()&&!this.used(x.source.id)&&Date.parse(x.source.time)>(this.history.data.task_source_cutoff||0)).map(x=>({id:x.source.id,username:x.source.username,message:x.source.message,valid_until:x.valid_until})),
   capacity_note:'Reply admission and autonomous hourly/provider capacity are separate. Task acceptance is not a planner-turn reservation.'};
 }
 persist(changes){const previous=this.history.data;this.history.data={...previous,...changes};try{this.history.save();}catch(error){this.history.data=previous;throw error;}}
 revokeSources(){this.persist({task_source_cutoff:this.now()});}
 used(id){return (this.history.data.task_authorizations||[]).some(r=>r.source.id===id)||(this.history.data.accepted_requests||[]).includes(id);}
 // Authenticated operator route only; never exposed as an agent tool. Retains
 // historical evidence with an explicit review, not invented transport proof.
 reviewSource({request_id,expected_source_hash,reason,valid_for_seconds=600}){
  if(!this.enabled()||this.history.data.turn)throw Error('Review requires enabled intake and an idle body');
  if(typeof reason!=='string'||reason.trim().length<8||reason.length>1000||!Number.isInteger(valid_for_seconds)||valid_for_seconds<1||valid_for_seconds>3600)throw Error('Bounded review reason/window required');
  const e=this.history.data.events.find(e=>e.id===request_id);
  if(!e||e.kind!=='chat'||e.source!=='human'||!e.accepted||e.whisper||e.provenance!=='minecraft_public_chat'||Date.parse(e.time)<=(this.history.data.task_source_cutoff||0)||this.used(request_id)||digest(e)!==expected_source_hash)throw Error('Exact unused public human source evidence required');
  const list=this.history.data.reviewed_task_sources||[];
  if(list.some(r=>r.source.id===request_id))throw Error('Source already reviewed; no implicit renewal');
  const r={source:JSON.parse(JSON.stringify(e)),source_hash:digest(e),reason,reviewed_at:this.now(),valid_until:this.now()+valid_for_seconds*1000,evidence_origin:'authenticated_operator_review'};
  this.persist({reviewed_task_sources:[...list,r]});return r;
 }
 source(id){
  const data=this.history.data,turn=data.turn;
  if(!this.enabled()||!turn?.conversation_only)throw Error('Task intake requires an enabled, bounded human conversation turn');
  this.limits();
  const review=(data.reviewed_task_sources||[]).find(r=>r.source.id===id&&r.valid_until>this.now());
  const e=review?.source||data.events.find(e=>e.id===id),at=Date.parse(e?.time);
  if(!e||e.kind!=='chat'||e.source!=='human'||e.accepted!==true||e.whisper||e.provenance!=='minecraft_public_chat'||!Number.isFinite(at)||at>this.now()+5000||at<=(data.task_source_cutoff||0))throw Error('A public human source is required');
  if(!review&&(!turn.request_ids.includes(id)||at<=this.now()-600000||e.transport?.kind!=='server_player_uuid'||e.transport?.username!==e.username||!e.transport.uuid))throw Error('Source must be fresh, bound to this turn and attributed by the game transport; historical sources require explicit operator review');
  const actor={kind:'human',name:e.username,server_player_uuid:e.transport?.uuid||null},audience={kind:'public',experience:'minecraft'};
  const original={id:e.id,actor,audience,message:e.message,time:e.time};
  return {...original,username:e.username,revision:digest(original),source_hash:digest(e),transport:e.transport||null,evidence_origin:review?'authenticated_operator_review':'server_player_uuid'};
 }
 receipt(operation,args){
  const old=(this.history.data.task_authorizations||[]).find(r=>r.source.id===args.request_id);
  if(!old)return null;
  if(old.operation!==operation||old.arguments_hash!==digest(args))throw Error('This source already authorized a different transition');
  return {...old.result,duplicate:true,current_status:this.history.task()?.id===old.result.task_id?this.history.task().status:'superseded'};
 }
 commit(operation,args,source,task,previous,changes={}){
  const result={task_id:task.id,status:task.status,authority_revision:task.authority_revision,turns:task.turns,max_turns:task.max_turns,deadline:task.deadline,accepted:true,execution_started:false};
  this.persist({...changes,task,task_authorizations:[...(this.history.data.task_authorizations||[]),{id:randomUUID(),at:this.now(),operation,source,arguments_hash:digest(args),previous,result}]});return result;
 }
 accept(args){
  const duplicate=this.receipt('accept',args);if(duplicate)return duplicate;
  const source=this.source(args.request_id),limits=this.limits(),old=this.history.task();
  if(this.requiresReview(old))throw Error('Unresolved interrupted work requires effects review before another assignment');
  if(old&&['running','waiting','blocked','needs_review'].includes(old.status))throw Error('Current assignment must be settled before accepting another');
  if(typeof args.goal!=='string'||!args.goal.trim()||args.goal.length>2000)throw Error('A bounded task goal is required');
  if(this.used(source.id))throw Error('Source already used');
  const max_turns=args.max_turns??limits.default_turns,seconds=args.seconds??limits.default_seconds;
  if(!Number.isInteger(max_turns)||max_turns<1||max_turns>limits.max_turns||!Number.isInteger(seconds)||seconds<120||seconds>limits.max_seconds)throw Error('Requested task limits exceed installation ceilings or are invalid');
  const task={id:randomUUID(),goal:args.goal,request_id:source.id,requested_by:source.username,request:source.message,status:'running',turns:0,max_turns,deadline:this.now()+seconds*1000,progress:[],started_at:new Date(this.now()).toISOString(),reviewers:[],rework_requests:[],authority_revision:1,authority:{kind:'human_game_request',source}};
  return this.commit('accept',args,source,task,null,{...(old?{task_history:[...(this.history.data.task_history||[]),old].slice(-10)}:{}),accepted_requests:[...(this.history.data.accepted_requests||[]),source.id]});
 }
 amend(args){
  const duplicate=this.receipt('amend',args);if(duplicate)return duplicate;
  const source=this.source(args.request_id),limits=this.limits(),task=this.history.task()?structuredClone(this.history.task()):null;
  if(this.used(source.id))throw Error('Source already used');
  if(this.requiresReview(task))throw Error('Unresolved interrupted work requires effects review before amendment');
  if(!task||task.id!==args.task_id||task.authority?.kind!=='human_game_request'||task.authority_revision!==args.expected_revision||['stopped','needs_review'].includes(task.status))throw Error('Task authority changed or requires recovery review');
  if(args.max_turns===undefined&&args.deadline===undefined)throw Error('Specify a cumulative cap or absolute deadline');
  const cap=args.max_turns??task.max_turns,deadline=args.deadline??task.deadline;
  if(!Number.isInteger(cap)||cap<0||cap>limits.max_turns||!Number.isSafeInteger(deadline)||deadline<=0||deadline>this.now()+limits.max_seconds*1000)throw Error('Amendment violates valid limits or installation ceilings');
  const exhausted=cap<=task.turns||deadline<=this.now();
  if(task.status==='budget_exhausted'&&!exhausted&&args.resume!==true)throw Error('Expired assignment needs an explicit human-requested resume amendment');
  const previous={status:task.status,max_turns:task.max_turns,deadline:task.deadline,turns:task.turns,authority_revision:task.authority_revision};
  task.max_turns=cap;task.deadline=deadline;task.authority_revision++;
  if(exhausted){task.status='budget_exhausted';task.wait_for=null;task.wait_started_at=null;}
  else if(args.resume===true){task.status='running';task.wait_for=null;task.wait_started_at=null;}
  return this.commit('amend',args,source,task,previous);
 }
}
module.exports={TaskIntake,INTAKE_TOOLS,digest};
