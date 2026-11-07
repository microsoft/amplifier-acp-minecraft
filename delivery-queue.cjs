// Expiry of a queued delivery is not incorporation of its source.
// Use the same source lifetimes as conversation admission; never expire human
// inputs here, infer a missing timestamp, or split an attention offer.
function retireExpired(history,inbox,now=Date.now()){
 if(history.data.turn)return {retired:0};
 const events=new Map(history.data.events.map(e=>[e.id,e]));
 const expired=m=>{
  if(m.source==='activity')return m.activity?.id===m.id&&Number.isSafeInteger(m.activity.occurred_at)&&m.activity.occurred_at>0&&now-m.activity.occurred_at>=120000;
  const e=events.get(m.id),at=Date.parse(e?.time);
  if(!Number.isFinite(at)||at>now)return false;
  if(m.source==='agent')return e?.source==='agent'&&e.kind==='chat'&&now-at>=600000;
  return false;
 };
 const key=m=>m.attention_offer?JSON.stringify(m.attention_offer):null;
 const retiring=inbox.filter(m=>expired(m)&&(!key(m)||inbox.filter(n=>key(n)===key(m)).every(expired)));
 if(!retiring.length)return {retired:0};
 const ids=new Set(retiring.map(m=>m.id));
 // Archive the original envelope and source with the queue mutation in the
 // same atomic history save. A restart cannot requeue or acknowledge them.
 history.data.delivery_retirements=[...(history.data.delivery_retirements||[]),...retiring.map(m=>({
  at:new Date(now).toISOString(),reason:'delivery_lifetime_elapsed',disposition:'undelivered',
  message:m,source:m.source==='activity'?m.activity:events.get(m.id)
 }))].slice(-64);
 for(let i=inbox.length-1;i>=0;i--)if(ids.has(inbox[i].id))inbox.splice(i,1);
 history.save();return {retired:retiring.length,ids:[...ids],disposition:'undelivered'};
}
module.exports={retireExpired};
