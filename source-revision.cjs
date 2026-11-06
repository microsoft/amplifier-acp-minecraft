// One immutable public-event identity for both attention and active awareness.
// Never hash the surrounding context, its truncation, or a receipt state.
const crypto=require('node:crypto');
const {isPublicChatEvent}=require('./public-chat.cjs');
function publicSource(event){
 if(!isPublicChatEvent(event)||typeof event.id!=='string'||!event.id)return null;
 const occurredAt=Date.parse(event.time);
 if(!Number.isSafeInteger(occurredAt)||occurredAt<=0)return null;
 const revision=crypto.createHash('sha256').update(JSON.stringify([
  event.id,event.time,event.kind,event.username||'',event.source||'',event.message??event.sent??''
 ])).digest('hex');
 return {id:event.id,revision,occurredAt};
}
module.exports={publicSource};
