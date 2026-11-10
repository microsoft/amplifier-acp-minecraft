// Domain-side operation identity only. The shared host authenticates room actors
// and owns canonical messages. This journal never grants work or handles input.
const crypto=require('node:crypto');
const {isPublicChatEvent}=require('./public-chat.cjs');
const {publicSource}=require('./source-revision.cjs');
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const hash=v=>crypto.createHash('sha256').update(JSON.stringify(canonical(v))).digest('hex');
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

class HuddleJournal {
 constructor(history,binding){
  for(const key of ['host','room_id','agent_id','connection_id'])if(typeof binding?.[key]!=='string'||!binding[key]||binding[key].length>256)throw Error('Fixed huddle participant binding required');
  this.history=history;this.binding=Object.fromEntries(['host','room_id','agent_id','connection_id'].map(k=>[k,binding[k]]));
  this.key=hash(this.binding);
 }
 records(){return this.history.data.huddle_operations?.[this.key]||{};}
 commit(id,record){
  const data=this.history.data,prior=data.huddle_operations;
  data.huddle_operations={...prior,[this.key]:{...this.records(),[id]:record}};
  try{this.history.save();}catch(error){if(prior===undefined)delete data.huddle_operations;else data.huddle_operations=prior;throw error;}
 }
 begin(payload){
  if(!uuid.test(payload?.request_id))throw Error('Stable huddle operation UUID required');
  const id=payload.request_id,existing=this.records()[id],payload_hash=hash(payload);
  if(existing){
   if(existing.payload_hash!==payload_hash)throw Error('Huddle operation already has a different payload');
   return {send:false,record:structuredClone(existing)};
  }
  const record={binding:this.binding,request_id:id,payload_hash,payload:structuredClone(payload),state:'unknown',started_at:new Date().toISOString()};
  // Persist before transport. After any loss, status is the only next operation;
  // even a 404 cannot prove the original request is no longer in flight.
  this.commit(id,record);return {send:true,record:structuredClone(record)};
 }
 saved(id,receipt){
  const existing=this.records()[id];if(!existing)throw Error('No original huddle operation');
  // The HTTP bridge must first validate the host's exact receipt and binding.
  // Here a receipt is evidence, never an incorporation/completion verdict.
  if(existing.state==='saved'){
   if(hash(existing.receipt)!==hash(receipt))throw Error('Saved huddle receipt changed');
   return structuredClone(existing);
  }
  const record={...existing,state:'saved',receipt:structuredClone(receipt)};this.commit(id,record);return structuredClone(record);
 }
 read(id){return structuredClone(this.records()[id]||{request_id:id,state:'unknown'});}
}

function publicReturnSource(history,enrollment,origin){
 // Owner enrollment freezes the origin; room observers and peer-supplied source
 // metadata cannot replace it. Private or foreign origins have no public return.
 if(!enrollment?.origin||hash(enrollment.origin)!==hash(origin)||origin.kind!=='external'||origin.service!=='minecraft'||origin.connection_id!==enrollment.connection_id||origin.conversation_id!==enrollment.conversation_id)throw Error('Outcome is not bound to this original Minecraft destination');
 const event=history.data.events.find(e=>e.id===origin.source_id)||(history.data.public_conversation_history||[]).find(e=>e.id===origin.source_id),source=publicSource(event);
 if(!event||!source||!isPublicChatEvent(event)||event.source!=='human'||event.accepted!==true||event.provenance!=='minecraft_public_chat'||event.transport?.kind!=='server_player_uuid'||event.transport.username!==event.username||!event.transport.uuid||origin.actor?.kind!=='human'||origin.actor.id!==event.transport.uuid||source.revision!==origin.source_revision||source.occurredAt!==origin.occurred_at)throw Error('Original authenticated public human source is unavailable or changed');
 return {source_fact:source,actor:{id:event.transport.uuid,label:event.username},audience:'minecraft_public_chat',connection_id:enrollment.connection_id,request_id:origin.request_id};
}

module.exports={HuddleJournal,publicReturnSource};
