// Public room provenance is set by the transport, never inferred from text.
function isPublicChatEvent(event){
 if(!event||event.whisper||!['chat','chat_sent'].includes(event.kind))return false;
 if(event.provenance!==undefined)return event.provenance==='minecraft_public_chat';
 // Earlier /task records had no provenance and were stored as Operator chat.
 // Explicit game provenance above still allows a real player with that name.
 return event.username!=='Operator';
}
module.exports={isPublicChatEvent};
