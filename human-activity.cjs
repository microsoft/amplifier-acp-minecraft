// Observed game activity, not mere presence and never a construction grant.
class HumanActivity {
 constructor(agentNames,{now=Date.now,activeMs=120000,onMovement=()=>{}}={}){this.onMovement=onMovement;this.agents=new Set(agentNames.map(x=>x.toLowerCase()));this.now=now;this.activeMs=activeMs;this.players=new Map();}
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
 snapshot(){const now=this.now();return {observed_at:now,active_window_ms:this.activeMs,
  players:[...this.players.values()].map(p=>({...p,active:p.last_activity_at!==null&&now-p.last_activity_at<this.activeMs})),
  scope:'Loaded server-attributed human movement. Idle presence is not activity; these observations do not create or renew tasks.'};}
}
module.exports={HumanActivity};
