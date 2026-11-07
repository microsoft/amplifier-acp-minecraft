// Transport/resource admission only. Instance still owns engage/hold decisions.
const REPLY_TOOLS=new Set(['observe','conversation','entities','inventory','inspect','read_sign','survey','map','plan_route','find','chat','task_capabilities']);
class ConversationAdmission {
 constructor(history,cfg,{now=Date.now}={}){this.history=history;this.cfg=cfg;this.now=now;}
 limit(){if(this.cfg.human_engagement?.enabled===true)return null;const n=this.cfg.human_reply_turns_per_hour??12;return Number.isInteger(n)&&n>=0&&n<=60?n:0;}
 recent(){return (this.history.data.conversation_admissions||[]).filter(r=>r.at>this.now()-3600000);}
 eligible(message){
  const data=this.history.data,e=data.events.find(e=>e.id===message.id),at=Date.parse(e?.time);
  return message.source==='human'&&e?.source==='human'&&e.kind==='chat'&&e.accepted===true&&
   ['minecraft_public_chat','minecraft_whisper'].includes(e.provenance)&&Number.isFinite(at)&&at<=this.now()+5000&&at>this.now()-600000&&
   !(data.conversation_admissions||[]).some(r=>r.ids.includes(message.id));
 }
 status(inbox){return {version:1,unmetered:this.limit()===null,remaining:this.limit()===null?null:Math.max(0,this.limit()-this.recent().length),
  eligible_ids:inbox.filter(m=>this.eligible(m)).map(m=>m.id),scope:'conversation_only'};}
 start(ids,inbox){
  if(this.history.data.turn||!Array.isArray(ids)||!ids.length||ids.length>8||new Set(ids).size!==ids.length||
   (this.limit()!==null&&!this.status(inbox).remaining)||ids.some(id=>!inbox.some(m=>m.id===id&&this.eligible(m))))throw Error('No fresh human conversation admission available');
  const selected=inbox.filter(m=>ids.includes(m.id));
  const audiences=new Set(selected.map(m=>m.whisper?'private:'+m.username:'public'));
  if(audiences.size!==1)throw Error('Reply audiences cannot be mixed');
  const offers=new Set(selected.map(m=>JSON.stringify(m.attention_offer||null)));
  if(offers.size!==1)throw Error('Distinct attention offers cannot share a reply turn');
  const offer=selected[0].attention_offer;
  if(offer&&inbox.some(m=>JSON.stringify(m.attention_offer||null)===JSON.stringify(offer)&&!ids.includes(m.id)))
   throw Error('An attention offer must remain whole; mixed peer offers wait for ordinary capacity');
  // One atomic durable reservation consumes source IDs even without a quota.
  // A lost response or restart must not submit these inputs again automatically.
  this.history.data.conversation_admissions=[...this.recent(),{at:this.now(),ids:[...ids]}];
  this.history.data.turn={started_at:new Date(this.now()).toISOString(),conversation_only:true,task_id:null,
   request_ids:[...ids],messages:selected,reply_recipient:selected[0].whisper?selected[0].username:null,actions:[],may_mutate:false};
  for(let i=inbox.length-1;i>=0;i--)if(ids.includes(inbox[i].id))inbox.splice(i,1);
  this.history.save();return this.history.data.turn;
 }
}
module.exports={ConversationAdmission,REPLY_TOOLS};
