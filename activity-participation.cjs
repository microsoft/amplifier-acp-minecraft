// Installation-scoped activity facts, separate from human speech and task grants.
const crypto=require('node:crypto');
const {ParticipationRejection}=require('./participation.cjs');
const TTL=120000,COALESCE=10000;
class ActivityParticipation {
 constructor(history,cfg,{now=Date.now}={}){this.history=history;this.cfg=cfg;this.now=now;}
 enabled(){return this.cfg.human_engagement?.enabled===true&&this.cfg.human_engagement?.activity_scope==='conversation_only'&&this.history.data.task?.status!=='stopped';}
 observe({uuid,name,from,to,at}){
  if(!this.enabled()||typeof uuid!=='string'||!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(uuid)||!name||(this.cfg.bot_names||[]).concat(this.cfg.username).some(n=>n.toLowerCase()===name.toLowerCase()))return;
  if(!Number.isSafeInteger(at)||at<=0||at>this.now()+5000||this.now()-at>TTL)return;
  if(![from,to].every(p=>p&&[p.x,p.y,p.z].every(Number.isFinite)))return;
  const data=this.history.data,tracks=data.activity_tracks||{},old=tracks[uuid];
  if(old&&at-old.at<COALESCE)return;
  const id=crypto.randomUUID(),actor='minecraft-player:'+uuid.toLowerCase();
  const point=p=>[p.x,p.y,p.z].map(Math.round).join(',');
  const fact={id,actor,kind:'movement',summary:`${name} moved from (${point(from)}) to (${point(to)}) in the observed game area.`,occurred_at:at};
  fact.revision=crypto.createHash('sha256').update(JSON.stringify(fact)).digest('hex');
  data.activity_tracks=Object.fromEntries(Object.entries({...tracks,[uuid]:{at}}).filter(([,v])=>this.now()-v.at<TTL));
  // Coalesce one latest observed source per actor. Human message queues are
  // untouched. An in-flight replaced ambient observation fails the exact recheck.
  data.activity_pending=[...(data.activity_pending||[]).filter(v=>v.fact.actor!==actor&&this.now()-v.fact.occurred_at<TTL),{fact,name}].slice(-16);
  this.history.save();
 }
 proposal(sourceId=null){
  if(!this.enabled())return null;
  const now=this.now(),row=(this.history.data.activity_pending||[]).find(r=>(!sourceId||r.fact.id===sourceId)&&now-r.fact.occurred_at<TTL);
  if(!row)return null;
  const context={conversation_id:this.cfg.conversation_id||'minecraft:workshop',agent:{id:this.cfg.username,name:this.cfg.username,is_agent:true},participants:[{id:this.cfg.username,name:this.cfg.username,is_agent:true},{id:row.fact.actor,name:row.name,is_agent:false}],messages:[],activities:[row.fact],trigger_id:row.fact.id};
  const signature=crypto.createHash('sha256').update(JSON.stringify(context)).digest('hex');
  return {context,signature,ids:[row.fact.id],occurred_at:row.fact.occurred_at,sources:[{id:row.fact.id,revision:row.fact.revision,occurredAt:row.fact.occurred_at}],effect_scope:'conversation_only'};
 }
 apply(result,inbox){
  const p=this.proposal(result.source_id);
  if(!p||p.signature!==result.signature)throw new ParticipationRejection('source_changed');
  if(!['engage','hold'].includes(result.action))throw new ParticipationRejection('invalid_action');
  if(result.action==='engage'){
   if(!result.offer?.id||!result.offer?.ticket)throw new ParticipationRejection('invalid_action');
   if(inbox.length>=8)throw new ParticipationRejection('inbox_full');
   const activity=p.context.activities[0];
   inbox.push({id:activity.id,source:'activity',activity,attention_offer:result.offer,effect_scope:'conversation_only'});
   this.history.data.activity_deliveries=[...(this.history.data.activity_deliveries||[]).filter(r=>this.now()-r.at<TTL),{id:activity.id,at:activity.occurred_at,revision:activity.revision}];
  }
  this.history.data.activity_pending=(this.history.data.activity_pending||[]).filter(r=>r.fact.id!==result.source_id);this.history.save();
  return {queued:result.action==='engage',action:result.action,source_id:result.source_id,acp_admitted:false};
 }
 clear(){this.history.data.activity_pending=[];this.history.save();}
}
module.exports={ActivityParticipation};
