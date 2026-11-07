// Observed game activity, not mere presence and never a construction grant.
class HumanActivity {
 constructor(agentNames,{now=Date.now,activeMs=120000,onMovement=()=>{},onInteraction=()=>{}}={}){this.onMovement=onMovement;this.onInteraction=onInteraction;this.agents=new Set(agentNames.map(x=>x.toLowerCase()));this.now=now;this.activeMs=activeMs;this.players=new Map();}
 sample(players){
  const now=this.now(),seen=new Set();
  for(const p of Object.values(players).slice(0,64)){
   if(!p?.username||this.agents.has(p.username.toLowerCase())||!p.uuid)continue;
   const pos=p.entity?.position;if(!pos||![pos.x,pos.y,pos.z].every(Number.isFinite))continue;
   seen.add(p.uuid);const old=this.players.get(p.uuid),position={x:pos.x,y:pos.y,z:pos.z};
   const moved=old&&Math.hypot(position.x-old.position.x,position.y-old.position.y,position.z-old.position.z)>=0.25;
   if(moved)this.onMovement({uuid:p.uuid,name:p.username,from:old.position,to:position,at:now});
   if(!old||moved)this.players.set(p.uuid,{name:p.username,position,last_activity_at:moved?now:old?.last_activity_at??null,kind:moved?'movement':null});
  }
  for(const id of this.players.keys())if(!seen.has(id))this.players.delete(id);
 }
 interaction(entity,players){
  // Server animation is an observed action, not inferred chat or task intent.
  // Match the current player entity by identity; mobs, stale entities and peers do not count.
  const p=Object.values(players).find(p=>p?.entity===entity&&p.uuid&&p.username&&!this.agents.has(p.username.toLowerCase()));
  const pos=entity?.position;
  if(!p||!pos||![pos.x,pos.y,pos.z].every(Number.isFinite))return;
  const now=this.now(),position={x:pos.x,y:pos.y,z:pos.z};
  this.players.set(p.uuid,{name:p.username,position,last_activity_at:now,kind:'interaction'});
  this.onInteraction({uuid:p.uuid,name:p.username,from:position,to:position,at:now,kind:'interaction'});
 }
 snapshot(){const now=this.now();return {observed_at:now,active_window_ms:this.activeMs,
  players:[...this.players.values()].map(p=>({...p,active:p.last_activity_at!==null&&now-p.last_activity_at<this.activeMs})),
  scope:'Loaded server-attributed human movement. Idle presence is not activity; these observations do not create or renew tasks.'};}
}
function updateEngagement(history,activity,now=Date.now()){
 const window=activity.active_window_ms;
 const inputs=history.data.events.filter(e=>{
  const at=Date.parse(e.time),t=e.transport;
  return e.kind==='chat'&&e.source==='human'&&Number.isFinite(at)&&at<=now&&now-at<600000&&
   ((t?.kind==='authenticated_operator_control'&&e.provenance==='operator_control')||
    (t?.kind==='server_player_uuid'&&t.username===e.username&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(t.uuid||'')));
 });
 const last=inputs.reduce((at,e)=>Math.max(at,Date.parse(e.time)),0),ids=new Set(inputs.map(e=>e.id));
 const pending=(history.data.inbox||[]).filter(m=>m.source==='human'&&ids.has(m.id)).length;
 return {version:1,active:pending>0||(last>0&&now-last<window)||activity.players.some(p=>p.active),
  pending_human_inputs:pending,last_message_at:last||null,active_window_ms:window};
}
module.exports={HumanActivity,updateEngagement};
