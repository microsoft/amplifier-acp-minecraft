// A human reply may use an existing assignment, never create one implicitly.
const bounds=require('./task-bounds.cjs');
function identity(task){
 return task?JSON.stringify([task.id,task.authority_revision,task.turns,bounds.get(task)]):null;
}
function bind(history,cfg,allowed){
 const turn=history.data.turn,task=history.task();
 if(cfg.human_engagement?.enabled!==true||!allowed||!turn?.conversation_only||turn.ambient_activity||turn.peer_proposal||!bounds.valid(task)||!['running','waiting'].includes(task?.status))return;
 const sources=turn.request_ids.map(id=>history.data.events.find(e=>e.id===id));
 if(!sources.length||sources.some(e=>e?.source!=='human'||!(e.transport?.kind==='server_player_uuid'&&e.transport.username===e.username&&e.transport.uuid||e.provenance==='operator_control'&&e.transport?.kind==='authenticated_operator_control')))return;
 turn.existing_work_binding=identity(task);history.save();
}
function available(turn,task,allowed){
 return !!(allowed&&turn?.conversation_only&&!turn.ambient_activity&&!turn.peer_proposal&&turn.existing_work_binding&&bounds.valid(task)&&['running','waiting'].includes(task?.status)&&turn.existing_work_binding===identity(task)&&bounds.within(task,{minimumMs:120000}));
}
function promote(history,allowed){
 const old=history.data.turn,task=history.task();
 if(!available(old,task,allowed))throw Error('Conversation-only: World effects need an unchanged existing assignment');
 // Persist the consumed allowance and bound work turn before any physical call.
 // On restart it follows ordinary work recovery, never effect-free reply recovery.
 const previous=structuredClone(history.data);
 task.turns++;task.status='running';
 history.data.turn={...old,conversation_only:false,reply_origin:true,task_id:task.id,
  progress_revision:task.progress_revision||0,may_mutate:true};
 try{history.save();}catch(error){history.data=previous;throw error;}
 return history.data.turn;
}
module.exports={bind,available,promote};
