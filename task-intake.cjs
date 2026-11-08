// Local world-execution authority. Social attention and ACP remain independent.
const {createHash,randomUUID}=require('node:crypto');
const {ConversationAdmission}=require('./conversation-admission.cjs');
const delegation=require('./delegation.cjs');
const bounds=require('./task-bounds.cjs');
const replyWork=require('./reply-work.cjs');
const INTAKE_TOOLS=new Set(['task_accept','task_amend','task_accept_help']);
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const digest=value=>createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
class TaskIntake {
 constructor(history,cfg,{now=Date.now,completionSupported=()=>false}={}){this.history=history;this.cfg=cfg;this.now=now;this.completionSupported=completionSupported;}
 enabled(){return this.cfg.human_task_intake?.enabled===true;}
 limits(){
  const p=this.cfg.human_task_intake||{},turns=this.cfg.task_max_turns||12,seconds=this.cfg.task_max_seconds||2400;
  const limits={default_turns:turns,default_seconds:seconds,max_turns:p.max_turns??turns,max_seconds:p.max_seconds??seconds};
  if(!Object.values(limits).every(v=>Number.isSafeInteger(v)&&v>0)||limits.max_turns<turns||limits.max_seconds<seconds||limits.max_turns>10000||limits.max_seconds>604800)throw Error('Invalid human task defaults/ceilings; inspect installation policy');
  if(p.default_bound_mode!==undefined&&!['finite','completion_bound'].includes(p.default_bound_mode))throw Error('Unknown default task bound mode');
  return {...limits,completion_bound:p.default_bound_mode==='completion_bound'};
 }
 requiresReview(task){
  if(task?.status==='needs_review')return true;
  const turn=this.history.data.last_turn;
  if(!task||turn?.task_id!==task.id||!turn.interrupted)return false;
  // Deadline expiry must not erase the unresolved interruption. Only the
  // existing explicit/settled-receipt review path can clear that evidence.
  return !(task.progress||[]).some(p=>['operator_recovery','receipt_reconciliation'].includes(p.kind)&&Date.parse(p.at)>=Date.parse(turn.started_at));
 }
 runnable(){const t=this.history.task();return !!(this.enabled()&&t?.authority?.kind==='human_game_request'&&['running','waiting'].includes(t.status)&&(!t.bounds||this.completionSupported())&&bounds.within(t,{now:this.now(),currentTurn:this.history.data.turn?.task_id===t.id}));}
 recoveryReviewAllowed(){
  const task=this.history.task();
  if(!bounds.valid(task)||task?.status!=='needs_review')return false;
  const facts=this.history.recoveryFacts();
  let policyValid=true;try{this.limits();}catch{policyValid=false;}
  // Inspection eligibility is not effect authority. Only the existing bounded
  // settled-receipt recovery path may reopen this same assignment.
  return !!(policyValid&&this.cfg.automatic_recovery&&task?.status==='needs_review'&&
   (this.enabled()?task.authority?.kind==='human_game_request':this.cfg.incoming_chat_only!==true)&&
   (!task.bounds||this.completionSupported())&&bounds.within(task,{now:this.now(),minimumMs:120000})&&
   facts.receipts_complete&&facts.actions_succeeded&&facts.recovery_attempts<2);
 }
 capabilities(){
  const enabled=this.enabled();let limits=null,policy_error=null;try{limits=this.limits();}catch(e){policy_error=e.message;}
  const configured_chat_only=this.cfg.incoming_chat_only===true,conversation_only=this.history.data.turn?.conversation_only===true,task=this.history.task();
  const helper_unavailable=limits?.completion_bound&&!this.completionSupported();
  const can_accept=enabled&&!policy_error&&!helper_unavailable&&!this.requiresReview(task)&&!['running','waiting','blocked','needs_review'].includes(task?.status);
  const can_amend=enabled&&!policy_error&&!this.requiresReview(task)&&task?.authority?.kind==='human_game_request'&&!['stopped','needs_review'].includes(task.status);
  const work_blocked_reason=this.requiresReview(task)?'unresolved_interruption':!enabled?(configured_chat_only?'installation_chat_only':null):!task?'no_accepted_assignment':task.authority?.kind!=='human_game_request'?'no_current_intake_authority':!bounds.valid(task)?'unknown_assignment_bounds':task.bounds&&!this.completionSupported()?'completion_bound_helpers_unavailable':bounds.timeLow(task,1,this.now())?'assignment_expired':bounds.turnsLow(task)&&!this.runnable()?'assignment_turn_cap':['stopped','needs_review','blocked','review'].includes(task.status)?'assignment_'+task.status:null;
  const reply_work_allowed=replyWork.available(this.history.data.turn,task,!policy_error&&!this.requiresReview(task)&&(enabled?this.runnable():!configured_chat_only));
  return {version:1,reply_work_allowed,mode:enabled?'human_requests':configured_chat_only?'chat_only':'legacy_work',
   configured_chat_only,conversation_only,task_intake_enabled:enabled&&!policy_error,
   can_accept,can_amend:!!can_amend,work_blocked_reason,recovery_review_allowed:this.recoveryReviewAllowed(),
   can_delegate_execution:false,can_accept_help:enabled&&delegation.enabled(this.cfg)&&can_accept,delegation_reason:'A helper may independently accept a fresh locally verified human authorization and peer proposal when enabled. Aggregate budgets and further delegation are unavailable.',
   delegation_sources:delegation.humans(this.history,this.cfg,this.now()).map(e=>({id:e.id,username:e.username,message:e.message,time:e.time})),
   autonomous_work_allowed:enabled?(!policy_error&&this.runnable()):!configured_chat_only,
   defaults:limits?{mode:limits.completion_bound?'completion_bound':'finite',turns:limits.completion_bound?null:limits.default_turns,seconds:limits.completion_bound?null:limits.default_seconds}:null,
   completion_bound_helpers:{available:this.completionSupported(),required:['watch-v2','continuation-v2']},
   ceilings:limits?{cumulative_turns:limits.max_turns,seconds_from_amendment:limits.max_seconds}:null,
   blocked_reason:policy_error?'invalid_task_policy':helper_unavailable?'completion_bound_helpers_unavailable':!enabled&&configured_chat_only?'installation_chat_only':conversation_only&&!reply_work_allowed?'reply_turn_no_world_effects':null,
   task_revision:task?.authority_revision??0,
   assignment:task?{id:task.id,status:task.status,consumed_turns:task.turns,cumulative_cap:task.max_turns,deadline:task.deadline,...(task.bounds?{bounds:task.bounds}:{}),...bounds.publicRemaining(task,this.now())}:null,
   capacity:{actions_per_turn:this.cfg.human_engagement?.enabled===true?null:24,autonomous_turns_per_hour:this.cfg.human_engagement?.enabled===true?null:30,reply_turns_per_hour:new ConversationAdmission(this.history,this.cfg).limit(),human_priority:this.cfg.human_engagement?.enabled===true,provider_remaining:null,provider_limits:'Enforced independently by the connected host/provider; remaining capacity is not known to this body.'},
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
  const operator=!review&&e?.provenance==='operator_control'&&e?.transport?.kind==='authenticated_operator_control';
  if(!e||e.kind!=='chat'||e.source!=='human'||e.accepted!==true||e.whisper||(!operator&&e.provenance!=='minecraft_public_chat')||!Number.isFinite(at)||at>this.now()+5000||at<=(data.task_source_cutoff||0))throw Error('A public human source is required');
  if(!review&&(!turn.request_ids.includes(id)||at<=this.now()-600000||(!operator&&(e.transport?.kind!=='server_player_uuid'||e.transport?.username!==e.username||!e.transport.uuid))))throw Error('Source must be fresh, bound to this turn and attributed by the game transport; historical sources require explicit operator review');
  const actor={kind:'human',name:e.username,server_player_uuid:e.transport?.uuid||null},audience=operator?{kind:'private',experience:'installation_control'}:{kind:'public',experience:'minecraft'};
  const original={id:e.id,actor,audience,message:e.message,time:e.time};
  return {...original,username:e.username,revision:digest(original),source_hash:digest(e),transport:e.transport||null,evidence_origin:review?'authenticated_operator_review':operator?'authenticated_operator_control':'server_player_uuid'};
 }
 receipt(operation,args){
  const old=(this.history.data.task_authorizations||[]).find(r=>r.source.id===args.request_id);
  if(!old)return null;
  if(old.operation!==operation||old.arguments_hash!==digest(args))throw Error('This source already authorized a different transition');
  return {...old.result,duplicate:true,current_status:this.history.task()?.id===old.result.task_id?this.history.task().status:'superseded'};
 }
 commit(operation,args,source,task,previous,changes={}){
  const result={task_id:task.id,status:task.status,authority_revision:task.authority_revision,turns:task.turns,max_turns:task.max_turns,deadline:task.deadline,...(task.bounds?{bounds:task.bounds}:{}),accepted:true,execution_started:false};
  this.persist({...changes,task,task_authorizations:[...(this.history.data.task_authorizations||[]),{id:randomUUID(),at:this.now(),operation,source,arguments_hash:digest(args),previous,result}]});return result;
 }
 acceptHelp(args){
  const duplicate=this.receipt('accept_help',args);if(duplicate)return duplicate;
  const turn=this.history.data.turn,root=delegation.humans(this.history,this.cfg,this.now()).find(e=>e.id===args.request_id);
  const peer=delegation.peer(this.history,this.cfg,{id:args.peer_request_id,source:'agent'},this.now());
  if(!turn?.conversation_only||turn.ambient_activity||!turn.request_ids.includes(args.peer_request_id)||!root||!peer)throw Error('Fresh original public human evidence and a bound authenticated peer request are required');
  if(Date.parse(peer.time)<Date.parse(root.time))throw Error('Peer proposal precedes its human authorization');
  if((this.history.data.accepted_delegation_sources||[]).includes(peer.id))throw Error('Peer proposal already consumed');
  if(args.budget_scope!=='independent_per_agent'||typeof args.authorization_quote!=='string'||args.authorization_quote.length<8||args.authorization_quote.length>600||!root.message.includes(args.authorization_quote))throw Error('Quote the original explicit helper authorization and use independently authorized per-agent limits; aggregate allocation is unsupported');
  const original={id:root.id,actor:{kind:'human',name:root.username,server_player_uuid:root.transport.uuid},audience:{kind:'public',experience:'minecraft'},message:root.message,time:root.time};
  const source={...original,username:root.username,revision:digest(original),source_hash:digest(root),transport:root.transport,evidence_origin:'server_player_uuid'};
  return this.accept(args,{source,peer:{id:peer.id,name:peer.username,transport:peer.transport,time:peer.time,message:peer.message,source_hash:digest(peer)},authorization_quote:args.authorization_quote,budget_scope:args.budget_scope,may_delegate_further:false});
 }
 accept(args,help=null){
  const operation=help?'accept_help':'accept',duplicate=this.receipt(operation,args);if(duplicate)return duplicate;
  const source=help?.source||this.source(args.request_id),limits=this.limits(),old=this.history.task();
  if(this.requiresReview(old))throw Error('Unresolved interrupted work requires effects review before another assignment');
  if(old&&['running','waiting','blocked','needs_review'].includes(old.status))throw Error('Current assignment must be settled before accepting another');
  if(typeof args.goal!=='string'||!args.goal.trim()||args.goal.length>2000)throw Error('A bounded task goal is required');
  if(this.used(source.id))throw Error('Source already used');
  const max_turns=args.max_turns===undefined?(limits.completion_bound?null:limits.default_turns):args.max_turns;
  const seconds=args.seconds===undefined?(limits.completion_bound?null:limits.default_seconds):args.seconds;
  if((max_turns===null?args.max_turns!==undefined:!Number.isInteger(max_turns)||max_turns<1||max_turns>limits.max_turns)||(seconds===null?args.seconds!==undefined:!Number.isInteger(seconds)||seconds<120||seconds>limits.max_seconds))throw Error('Requested task limits exceed installation ceilings or are invalid');
  if(limits.completion_bound&&!this.completionSupported())throw Error('Completion-bound work requires discovered watch-v2 and continuation-v2 helpers');
  const deadline=seconds===null?null:(help?Date.parse(source.time):this.now())+seconds*1000;
  if(help&&deadline!==null&&deadline-this.now()<120000)throw Error('Original helper allowance has insufficient time; no renewed deadline');
  const task={id:randomUUID(),goal:args.goal,request_id:source.id,requested_by:source.username,request:source.message,status:'running',turns:0,progress:[],started_at:new Date(this.now()).toISOString(),reviewers:[],rework_requests:[],authority_revision:1,authority:{kind:'human_game_request',source,...(help?{delegation:help}:{})}};
  if(limits.completion_bound)bounds.set(task,deadline===null?bounds.unbounded():bounds.finite(deadline),max_turns===null?bounds.unbounded():bounds.finite(max_turns));
  else {task.max_turns=max_turns;task.deadline=deadline;}

  return this.commit(operation,args,source,task,null,{...(help?{accepted_delegation_sources:[...(this.history.data.accepted_delegation_sources||[]),help.peer.id]}:{}),...(old?{task_history:[...(this.history.data.task_history||[]),old].slice(-10)}:{}),accepted_requests:[...(this.history.data.accepted_requests||[]),source.id]});
 }
 amend(args){
  const duplicate=this.receipt('amend',args);if(duplicate)return duplicate;
  const source=this.source(args.request_id),limits=this.limits(),task=this.history.task()?structuredClone(this.history.task()):null;
  if(this.used(source.id))throw Error('Source already used');
  if(this.requiresReview(task))throw Error('Unresolved interrupted work requires effects review before amendment');
  if(!task||task.id!==args.task_id||task.authority?.kind!=='human_game_request'||task.authority_revision!==args.expected_revision||['stopped','needs_review'].includes(task.status))throw Error('Task authority changed or requires recovery review');
  if(args.max_turns===undefined&&args.deadline===undefined)throw Error('Specify a cumulative cap or absolute deadline');
  const original=bounds.get(task),cap=args.max_turns===undefined?original.max_turns:bounds.finite(args.max_turns),deadline=args.deadline===undefined?original.deadline_ms:bounds.finite(args.deadline);
  bounds.validate(cap);bounds.validate(deadline);
  if((args.max_turns!==undefined&&args.max_turns>limits.max_turns)||(args.deadline!==undefined&&(args.deadline<=0||args.deadline>this.now()+limits.max_seconds*1000)))throw Error('Amendment violates valid limits or installation ceilings');
  const exhausted=(cap.kind==='finite'&&cap.value<=task.turns)||(deadline.kind==='finite'&&deadline.value<=this.now());
  if(task.status==='budget_exhausted'&&!exhausted&&args.resume!==true)throw Error('Expired assignment needs an explicit human-requested resume amendment');
  const previous={status:task.status,max_turns:task.max_turns,deadline:task.deadline,turns:task.turns,authority_revision:task.authority_revision,...(task.bounds?{bounds:structuredClone(task.bounds)}:{})};
  if(task.bounds)bounds.set(task,deadline,cap);else {task.max_turns=cap.value;task.deadline=deadline.value;}
  task.authority_revision++;
  if(exhausted){task.status='budget_exhausted';task.wait_for=null;task.wait_started_at=null;}
  else if(args.resume===true){task.status='running';task.wait_for=null;task.wait_started_at=null;}
  return this.commit('amend',args,source,task,previous);
 }
}
module.exports={TaskIntake,INTAKE_TOOLS,digest};
