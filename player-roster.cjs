// Server roster transitions are observations, never speech or task authority.
const {agentIdentity}=require('./agent-identity.cjs');
class PlayerRoster {
 // agents: the installation's agent identity, or a bare list of configured names.
 constructor(bot,agents,isReady,record){
  const identity=agentIdentity(agents);this.members=new Map();
  const described=p=>{
   if(!p?.username)return null;
   // classified_by says why: configured | server_offline_uuid | human_override | unknown.
   const {kind,classified_by}=identity.classify(p.username,p.uuid);
   return {username:p.username,uuid:p.uuid||null,source:kind==='agent'?'agent':p.uuid?'human':'unknown',classified_by,provenance:'server_player_roster'};
  };
  bot.on('spawn',()=>{this.members=new Map(Object.values(bot.players).map(described).filter(Boolean).map(p=>[p.username,p]));});
  bot.on('end',()=>this.members.clear());
  bot.on('playerJoined',p=>{
   const fact=described(p);if(!isReady()||!fact||this.members.has(fact.username))return;
   this.members.set(fact.username,fact);record('player_joined',fact);
  });
  bot.on('playerLeft',p=>{
   const fact=this.members.get(p?.username);if(!isReady()||!fact)return;
   this.members.delete(fact.username);record('player_left',fact);
  });
 }
}
module.exports={PlayerRoster};
