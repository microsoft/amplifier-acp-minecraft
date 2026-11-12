// Installation-owned permission to play. Tasks describe work; they are not
// required tickets for ordinary activity. This never changes a stored task.
function enabled(cfg){return cfg.human_engagement?.enabled===true&&cfg.human_engagement?.task_optional===true;}
function reason(history,cfg){
 if(!enabled(cfg))return 'task_optional_disabled';
 if(history.data.activity_stop)return 'explicit_stop';
 const turn=history.data.last_turn;
 if(turn?.activity&&(turn.interrupted||turn.actions?.some(a=>a.status==='pending'||a.status==='uncertain'&&a.review?.outcome!=='no_effect'&&!(turn.effect_review?.future_work_only&&['settled_failed_movement','settled_failed_storage'].includes(a.review?.outcome)))))return 'unresolved_activity_effects';
 // A separate activity cannot hide unsettled effects from an existing task.
 if(turn&&!turn.activity&&turn.interrupted&&turn.actions?.some(a=>a.status!=='succeeded'))return 'unresolved_task_effects';
 return null;
}
function allowed(history,cfg){return reason(history,cfg)===null;}
function canContinue(history,cfg){return allowed(history,cfg)&&!history.data.last_turn?.effect_review?.future_work_only&&history.data.last_turn?.activity===true&&history.data.last_turn?.activity_report?.status==='running';}
function promote(history,cfg){
 if(!allowed(history,cfg)||!history.data.turn?.conversation_only)throw Error('Ordinary activity is stopped or has unresolved effects');
 history.data.turn={...history.data.turn,conversation_only:false,activity:true,task_id:null,may_mutate:true};history.save();
}
function resume(history,cfg,{request_id,reason:explanation}){
 const stop=history.data.activity_stop,turn=history.data.turn;
 const source=history.data.events.find(e=>e.id===request_id);
 const verified=source?.transport?.kind==='server_player_uuid'&&source.transport.username===source.username&&source.transport.uuid||source?.provenance==='operator_control'&&source.transport?.kind==='authenticated_operator_control';
 if(!enabled(cfg)||!stop||!turn?.conversation_only||!turn.request_ids?.includes(request_id)||source?.source!=='human'||!source.accepted||!verified||Date.parse(source.time)<=stop.at||Date.now()-Date.parse(source.time)>600000||typeof explanation!=='string'||!explanation.trim())throw Error('Resuming after Stop requires a fresh current human instruction explicitly permitting activity');
 history.data.activity_stop_history=[...(history.data.activity_stop_history||[]),{...stop,resumed_by:request_id,reason:explanation}];
 delete history.data.activity_stop;history.save();
 return {resumed:true,task_changed:false,activity_allowed:allowed(history,cfg),blocked_reason:reason(history,cfg)};
}
// Authenticated owner control only: exact settled turn, no replay, no task or
// Stop amendment. Keep the original uncertain receipt alongside the review.
function reviewNoEffect(history,cfg,{expected_turn_sha256,action_id,reason:explanation}){
 const crypto=require('node:crypto'),turn=history.data.last_turn;
 const digest=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex');
 if(!enabled(cfg)||history.data.turn||!turn?.activity||turn.interrupted||digest(turn)!==expected_turn_sha256)throw Error('Exact idle settled activity review required');
 const action=turn.actions?.find(a=>a.id===action_id);
 if(!action||action.status!=='uncertain'||action.review||turn.actions.some(a=>a!==action&&a.status!=='succeeded'))throw Error('Review requires one uncertain action with all other actions succeeded');
 if(typeof explanation!=='string'||!explanation.trim()||explanation.length>2000)throw Error('Concrete no-effect evidence required');
 action.review={outcome:'no_effect',reason:explanation,reviewed_at:new Date().toISOString(),original_turn_sha256:expected_turn_sha256};history.save();
 return {action_id,review:action.review,task_changed:false,replayed:false,activity_allowed:allowed(history,cfg),blocked_reason:reason(history,cfg)};
}
module.exports={enabled,reason,allowed,canContinue,promote,resume,reviewNoEffect};
