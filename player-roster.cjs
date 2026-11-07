// Server roster transitions are observations, never speech or task authority.
class PlayerRoster {
 constructor(bot,agentNames,isReady,record){
  const agents=new Set(agentNames.map(n=>n.toLowerCase()));this.members=new Map();
  const described=p=>p?.username?{username:p.username,uuid:p.uuid||null,source:agents.has(p.username.toLowerCase())?'agent':p.uuid?'human':'unknown',provenance:'server_player_roster'}:null;
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
