function addressed(message,name,group=true){
  const n=name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  return new RegExp('^(?:(?:hey|hi|hello)[, ]+)?@?'+n+'(?:[^a-zA-Z0-9_]|$)','i').test(message)
    || new RegExp('@'+n+'\\b','i').test(message)
    || (group&&/^(everyone|team|agents)[,:!\s]/i.test(message));
}
// Each body keeps only its own conversational attention, never a shared agent brain.
// A direct address to someone else hands off this human's conversational focus.
function conversationRouter(name, {windowMs=600000,aliases={}}={}) {
  const matches=(message,person)=>[person,...(aliases[person]||[])].some(n=>addressed(message,n,false));
  const active=new Map();
  return ({username,message,whisper=false,participants=[],now=Date.now()})=>{
    for(const [person,until] of active)if(until<=now)active.delete(person);
    if(whisper){active.set(username,now+windowMs);return 'whisper';}
    if(matches(message,name)){active.set(username,now+windowMs);return 'direct';}
    if(participants.some(other=>other!==name&&matches(message,other))){
      active.delete(username);return null;
    }
    if(/^(everyone|team|agents)[,:!\s]/i.test(message)){
      // A group address wakes everyone, but does not attach future ambiguous chat
      // to every agent in the room.
      return 'group';
    }
    if(active.has(username)){active.set(username,now+windowMs);return 'followup';}
    return null;
  };
}
// These markers are ordinary public chat, visible to humans and other clients.
function peerIntent(message,name){
 const n=name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 const match=message.match(new RegExp('^@'+n+'\\s+\\[(FYI|ACK)\\]\\s','i'));
 return match?match[1].toUpperCase()==='FYI'?'update':'ack':'request';
}
module.exports={addressed,conversationRouter,peerIntent};
