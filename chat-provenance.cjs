// Attribution from the game's player registry and message event, not display text.
// This is server attribution, not a claim of Mojang signature verification.
class ChatProvenance {
 constructor(){this.messages=new WeakMap();}
 observe(message,position,sender,verified,players){
  if(!message||typeof message!=='object'||position!=='chat'||typeof sender!=='string'||!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(sender))return;
  const found=Object.entries(players||{}).find(([,p])=>p.uuid?.toLowerCase()===sender.toLowerCase());
  if(found)this.messages.set(message,{kind:'server_player_uuid',username:found[0],uuid:sender.toLowerCase(),signature_verified:verified===true});
 }
 get(username,message){const p=message&&typeof message==='object'?this.messages.get(message):null;return p?.username===username?{...p}:null;}
}
module.exports={ChatProvenance};
