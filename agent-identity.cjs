// The one decision point for "is this player an agent or a human?".
// Sources, in order: the operator's human override, explicit configuration, then
// the server-attested account kind when that policy is enabled. A player no
// source vouches for stays a human; nothing here guesses from names or text.
const crypto=require('node:crypto');
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// Java's UUID.nameUUIDFromBytes("OfflinePlayer:"+name): what a server or proxy
// derives for an unauthenticated login. The name is case-sensitive.
function offlineUuid(username){
 const b=crypto.createHash('md5').update('OfflinePlayer:'+username,'utf8').digest();
 b[6]=(b[6]&0x0f)|0x30;b[8]=(b[8]&0x3f)|0x80;
 const h=b.toString('hex');
 return [h.slice(0,8),h.slice(8,12),h.slice(12,16),h.slice(16,20),h.slice(20)].join('-');
}
const lower=name=>name.toLowerCase();
function names(value,key){
 if(value===undefined||value===null)return [];
 if(!Array.isArray(value)||value.some(n=>typeof n!=='string'))throw Error(key+' must be a list of player names');
 return value.filter(Boolean);
}
class AgentIdentity {
 // players: a function returning the server's current player list (mineflayer
 // bot.players, keyed by username). Without it only configuration applies.
 constructor(cfg={},{players=null}={}){
  const self=typeof cfg.username==='string'&&cfg.username?[cfg.username]:[];
  this.humans=new Set(names(cfg.human_names,'human_names').map(lower));
  if(self.some(n=>this.humans.has(lower(n))))throw Error("human_names cannot include this installation's own username");
  // Configured spellings, own username first; matching ignores case as before.
  this.listed=[...new Set([...self,...names(cfg.bot_names,'bot_names')])].filter(n=>!this.humans.has(lower(n)));
  this.configured=new Set(this.listed.map(lower));
  // Off unless exactly true: on a fully offline server humans have offline
  // UUIDs too, and would lose their authority.
  this.offline=cfg.agent_identity?.offline_uuid===true;
  this.players=players;this.derived=new Map();
 }
 roster(){const p=this.players?.();return p&&typeof p==='object'?p:{};}
 // Only what the server lists for this exact name, never an id from message text.
 observedUuid(username){const r=this.roster();return Object.hasOwn(r,username)?r[username]?.uuid:undefined;}
 derive(username){
  let id=this.derived.get(username);
  if(!id){if(this.derived.size>=1024)this.derived.clear();id=offlineUuid(username);this.derived.set(username,id);}
  return id;
 }
 // uuid must be server-observed (player list or recorded chat transport). When
 // omitted, the current player list is consulted; unknown stays configuration-only.
 classify(username,uuid){
  if(typeof username!=='string'||!username)return {kind:'human',classified_by:'unknown'};
  const key=lower(username);
  if(this.humans.has(key))return {kind:'human',classified_by:'human_override'};
  if(this.configured.has(key))return {kind:'agent',classified_by:'configured'};
  if(this.offline){
   const observed=uuid||this.observedUuid(username);
   if(typeof observed==='string'&&UUID.test(observed)&&lower(observed)===this.derive(username))return {kind:'agent',classified_by:'server_offline_uuid'};
  }
  // SEAM for future sources (for example self-announcement): add them here,
  // after the rules above, so the override and precedence stay in one place.
  // A new source must not turn an unverifiable claim into agent status.
  return {kind:'human',classified_by:'unknown'};
 }
 isAgent(username,uuid){return this.classify(username,uuid).kind==='agent';}
 // Configured spellings first, then agents the server currently lists. An
 // attested agent that has left is no longer named here.
 agentNames(){
  const out=[...this.listed];
  if(this.offline)for(const [name,p] of Object.entries(this.roster()).slice(0,256))if(!out.includes(name)&&this.classify(name,p?.uuid).classified_by==='server_offline_uuid')out.push(name);
  return out;
 }
 canonical(name){
  if(typeof name!=='string'||!name)return undefined;
  const key=lower(name);return this.agentNames().find(n=>lower(n)===key);
 }
 policy(){return {offline_uuid:this.offline};}
}
const instances=new WeakMap();
// One instance per configuration object, so every module that already receives
// cfg shares the live player list the body attaches. A bare list of names is
// explicit configuration only.
function agentIdentity(source,options){
 if(source instanceof AgentIdentity)return source;
 if(Array.isArray(source))return new AgentIdentity({bot_names:source});
 let identity=instances.get(source);
 if(!identity)instances.set(source,identity=new AgentIdentity(source,options));
 else if(options?.players)identity.players=options.players;
 return identity;
}
module.exports={AgentIdentity,agentIdentity,offlineUuid};
