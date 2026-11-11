// Installation-scoped room discovery and source-bound creation. No task grants.
const crypto=require('node:crypto');
const {Huddle:Room,associatedWork}=require('./huddle.cjs');
const {HuddleHttp,HuddleInstallationHttp}=require('./huddle-http.cjs');
const {HuddleJournal,publicReturnSource}=require('./huddle-journal.cjs');
const {publicSource}=require('./source-revision.cjs');
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const hash=v=>crypto.createHash('sha256').update(JSON.stringify(canonical(v))).digest('hex');
const same=(a,b)=>hash(a)===hash(b);
const text=(v,n)=>typeof v==='string'&&!!v.trim()&&Buffer.byteLength(v)<=n;
function roomSource(host,room,m){
 const identity=hash([host,room,m.id]);
 const id=[identity.slice(0,8),identity.slice(8,12),'5'+identity.slice(13,16),'a'+identity.slice(17,20),identity.slice(20,32)].join('-');
 return {id,revision:hash([room,m.id,m.seq,m.role,m.actor,m.agent_id,m.text,m.created_at,m.target_agent_ids,m.source,m.kind,m.outcome]),occurredAt:m.created_at};
}
class AutomaticHuddles {
 constructor(history,config,options={}){
  for(const k of ['installation_id','agent_id','connection_id','conversation_id','namespace'])if(!text(config?.[k],256))throw Error('Fixed installation huddle identity required');
  this.history=history;this.config=config;this.options=options;this.http=options.transport||new HuddleInstallationHttp(config,{timeoutMs:5000});
  this.key=hash([this.http.host,config.installation_id,config.agent_id,config.connection_id,config.conversation_id,config.namespace]);
  this.rooms=new Map();this.rosterValue=null;this.syncing=null;
  this.journal=new HuddleJournal(history,{host:this.http.host,room_id:'installation:'+config.installation_id,agent_id:config.agent_id,connection_id:config.connection_id});
 }
 state(){return this.history.data.automatic_huddles?.[this.key]||{rooms:{},pending:[],settled:{},sweep:0,next_room:0};}
 commit(state){const before=this.history.data.automatic_huddles;this.history.data.automatic_huddles={...before,[this.key]:state};try{this.history.save();}catch(e){if(before===undefined)delete this.history.data.automatic_huddles;else this.history.data.automatic_huddles=before;throw e;}}
 summary(){return {configured:true,automatic:true,read_tool:'huddle',rooms:Object.values(this.state().rooms).slice(-16).map(r=>({id:r.descriptor.id,purpose:r.descriptor.purpose,state:r.descriptor.state,membership:r.membership,observed_at:r.observed_at,inspect_url:r.descriptor.inspect_url})),pending_sources:this.state().pending.length,scope:'Room coordination only; existing world authority and original return destination remain independent.'};}
 async roster(){
  const r=await this.http.roster(),own=r?.installation;
  if(r?.version!==1||r.capabilities?.automatic!==1||!Array.isArray(r.items)||r.items.length>256||!own||own.id!==this.config.installation_id||own.agent_id!==this.config.agent_id||own.connection_id!==this.config.connection_id||own.conversation_id!==this.config.conversation_id||own.namespace!==this.config.namespace||own.service!=='minecraft')throw Error('Automatic huddle roster does not match installed identity');
  if(r.items.some(p=>!text(p.id,256)||!text(p.agent_id,256)||!text(p.connection_id,256)||p.namespace!==this.config.namespace||p.enabled!==true||p.availability!=='unknown')||new Set(r.items.map(p=>p.id)).size!==r.items.length)throw Error('Invalid enrolled huddle peers');
  this.rosterValue=r;return r;
 }
 origin(sourceId){
  const d=this.history.data,t=d.turn;
  const e=d.events.find(e=>e.id===sourceId)||(d.public_conversation_history||[]).find(e=>e.id===sourceId),s=publicSource(e);
  const current=t&&(t.request_ids?.includes(sourceId)||t.huddle_source_id===sourceId||(!t.activity&&t.task_id===d.task?.id&&d.task?.authority?.source?.id===sourceId&&['running','waiting'].includes(d.task.status)));
  if(!s||!current)throw Error('Choose a retained original human source associated with current work; do not reconstruct or refresh one');
  const origin={kind:'external',service:'minecraft',connection_id:this.config.connection_id,conversation_id:this.config.conversation_id,request_id:sourceId,source_id:s.id,source_revision:s.revision,occurred_at:s.occurredAt,actor:{id:e.transport?.uuid,kind:'human'}};
  publicReturnSource(this.history,{...this.config,origin},origin);return origin;
 }
 room(id){
  const row=this.state().rooms[id];if(!row||row.membership!=='active')throw Error('No current discovered room membership');
  let r=this.rooms.get(id);
  if(!r){const cfg={...this.config,room_id:id,origin:row.descriptor.origin};r=new Room(this.history,cfg,{...this.options,transport:this.options.roomTransport?.(id)||new HuddleHttp(cfg,{timeoutMs:5000}),onState:d=>this.observe(d,'active')});this.rooms.set(id,r);}
  return r;
 }
 observe(d,membership='active'){
  if(membership==='revoked')return this.revoke(d);
  if(!d||d.version!==1||!text(d.id,160)||d.conversation_id!==d.id||!['open','stopped'].includes(d.state)||!Number.isSafeInteger(d.revision)||d.revision<1||!d.origin||!['active','revoked'].includes(membership))throw Error('Invalid discovered room binding');
  if(membership==='active'&&(d.participant?.agent_id!==this.config.agent_id||d.participant?.connection_id!==this.config.connection_id))throw Error('Room participant does not match installation');
  const state=structuredClone(this.state()),old=state.rooms[d.id];
  if(old&&!same(old.descriptor.origin,d.origin))throw Error('Room original source changed');
  if(old&&(d.revision<old.descriptor.revision||old.membership==='revoked'&&membership==='active'))return;
  if(old&&d.revision===old.descriptor.revision&&old.descriptor.state==='stopped'&&d.state==='open')return;
  state.rooms[d.id]={...old,descriptor:structuredClone(d),membership,cursor:old?.cursor||0,observed_at:new Date().toISOString()};
  if(membership==='revoked'||d.state==='stopped'){
   for(const p of state.pending.filter(p=>p.room_id===d.id))state.settled[p.source.id]={reason:membership==='revoked'?'revoked':'stopped',at:Date.now()};
   state.pending=state.pending.filter(p=>p.room_id!==d.id);
  }
  const inbox=this.history.data.inbox,priorInbox=inbox?.slice();
  if(inbox&&(membership==='revoked'||d.state==='stopped')){for(let i=inbox.length-1;i>=0;i--)if(inbox[i].source==='huddle'&&inbox[i].room_id===d.id){const m=inbox[i];state.settled[m.id]={...state.settled[m.id],reason:membership==='revoked'?'revoked':'stopped',at:Date.now()};inbox.splice(i,1);}}
  try{this.commit(state);}catch(e){if(inbox)inbox.splice(0,inbox.length,...priorInbox);throw e;}
  this.options.onState?.(membership==='revoked'?{...d,state:'stopped'}:d);
 }
 revoke(d){
  if(d?.version!==1||!text(d.id,160)||d.participant?.agent_id!==this.config.agent_id||d.participant?.connection_id!==this.config.connection_id)throw Error('Revocation does not match installed participant');
  const state=structuredClone(this.state()),old=state.rooms[d.id],inbox=this.history.data.inbox,priorInbox=inbox?.slice();
  state.rooms[d.id]={...old,descriptor:old?.descriptor?{...old.descriptor,state:'stopped'}:{id:d.id,state:'stopped'},membership:'revoked',cursor:old?.cursor||0,observed_at:new Date().toISOString()};
  for(const p of state.pending.filter(p=>p.room_id===d.id))state.settled[p.source.id]={reason:'revoked',at:Date.now()};
  state.pending=state.pending.filter(p=>p.room_id!==d.id);
  if(inbox)for(let i=inbox.length-1;i>=0;i--)if(inbox[i].source==='huddle'&&inbox[i].room_id===d.id){const m=inbox[i];state.settled[m.id]={...state.settled[m.id],reason:'revoked',at:Date.now()};inbox.splice(i,1);}
  try{this.commit(state);}catch(e){if(inbox)inbox.splice(0,inbox.length,...priorInbox);throw e;}
  this.options.onState?.(state.rooms[d.id].descriptor);
 }
 async ensure(a){
  if(Object.keys(a).some(k=>!['request_id','source_id','title','purpose','peer_installation_ids'].includes(k)))throw Error('Unsupported ensure fields');
  const prior=this.journal.read(a.request_id);
  if(prior.payload){
   const payload={...prior.payload,title:a.title,purpose:a.purpose,peer_installation_ids:a.peer_installation_ids||[]};
   if(a.source_id!==payload.origin.source_id)throw Error('Ensure original source changed');this.journal.begin(payload);return this.ensureStatus(a.request_id);
  }
  if(!this.options.canPost?.())throw Error('A current controlling turn is required');
  const roster=await this.roster(),peers=a.peer_installation_ids||[];
  if(!text(a.title,200)||!text(a.purpose,2000)||!Array.isArray(peers)||peers.length>7||new Set(peers).size!==peers.length||peers.some(id=>!roster.items.some(p=>p.id===id)))throw Error('Select bounded approved installation peers');
  const payload={request_id:a.request_id,title:a.title,purpose:a.purpose,origin:this.origin(a.source_id),peer_installation_ids:peers};
  const unsettled=Object.values(this.journal.records()).find(r=>r.state==='unknown'&&r.payload?.origin?.source_id===a.source_id);
  if(unsettled)throw Error(`Original room creation is uncertain; query ensure_status with ${unsettled.request_id}`);
  this.journal.begin(payload);
  try{const d=await this.http.ensure(payload);return this.ensureSaved(a.request_id,d);}catch{throw Error('Room creation outcome unknown; use ensure_status with the SAME request_id');}
 }
 ensureSaved(id,d){
  const record=this.journal.read(id);
  if(!record.payload||d?.version!==1||d.request_id!==id||d.status!=='saved'||typeof d.reused!=='boolean'||!['active','revoked'].includes(d.membership)||!text(d.id,160)||d.participant?.agent_id!==this.config.agent_id||d.participant?.connection_id!==this.config.connection_id)throw Error('Ensure receipt does not match original operation');
  if(d.membership==='active'&&!same(d.origin,record.payload.origin))throw Error('Ensure receipt does not match original source');
  this.observe(d,d.membership);
  this.journal.saved(id,{version:1,request_id:id,room_id:d.id,installation_id:this.config.installation_id,reused:d.reused});
  return {state:'saved',membership:this.state().rooms[d.id].membership,room:this.state().rooms[d.id].descriptor,delivery:'not_established'};
 }
 async ensureStatus(id){const r=this.journal.read(id);if(!r.payload)return {request_id:id,state:'unknown',reason:'no_local_operation'};const result=await this.http.ensureStatus(id);if(!result.found)return {request_id:id,state:'unknown',reason:'not_found_is_not_permission_to_resend'};return this.ensureSaved(id,result.value);}
 async sync(){if(this.syncing)return this.syncing;this.syncing=this.refresh();try{return await this.syncing;}finally{this.syncing=null;}}
 async refresh(){
  await this.roster();const state=this.state(),page=await this.http.discovery(state.sweep,16);
  if(page?.version!==1||page.coverage!=='current_memberships'||!Array.isArray(page.items)||page.items.length>16||!Number.isSafeInteger(page.cursor)||page.cursor<state.sweep||typeof page.has_more!=='boolean'||(page.has_more&&page.cursor===state.sweep))throw Error('Invalid room discovery coverage');
  for(const d of page.items)this.observe(d,d.membership);
  let next=structuredClone(this.state());next.sweep=page.has_more?page.cursor:0;this.commit(next);
  const rooms=Object.values(this.state().rooms).filter(r=>r.membership==='active'&&r.descriptor.state==='open'),start=this.state().next_room;
  // Two rooms per existing-loop observation; no unbounded per-prompt fan-out.
  for(let i=0;i<Math.min(2,rooms.length);i++){
   const row=rooms[(start+i)%rooms.length];
   if(this.state().pending.length>=40)break;
   const page=await this.room(row.descriptor.id).read(row.cursor,Math.min(20,40-this.state().pending.length));this.ingest(row.descriptor.id,page);
  }
  next=structuredClone(this.state());next.next_room=rooms.length?(start+2)%rooms.length:0;this.commit(next);return this.summary();
 }
 ingest(id,page){
  const state=structuredClone(this.state()),row=state.rooms[id];if(!row||row.membership!=='active'||row.descriptor.state!=='open')return;
  for(const m of page.items){
   if(m.agent_id===this.config.agent_id||(m.target_agent_ids?.length&&!m.target_agent_ids.includes(this.config.agent_id)))continue;
   if(!Array.isArray(m.target_agent_ids)||m.target_agent_ids.some(v=>typeof v!=='string')||!['user','assistant'].includes(m.role)||m.status!=='complete')throw Error('Invalid completed room message');
   const source=roomSource(this.http.host,id,m),old=state.pending.find(p=>p.source.id===source.id);
   if(old&&!same(old.source,source))throw Error('Immutable room message changed');
   if(!old&&!state.settled[source.id])state.pending.push({room_id:id,source,message:structuredClone(m)});
  }
  row.cursor=page.next_cursor;this.commit(state);
 }
 proposal(sourceId=null){
  const p=this.state().pending.find(p=>!sourceId||p.source.id===sourceId);if(!p)return null;
  const row=this.state().rooms[p.room_id];if(!row||row.membership!=='active'||row.descriptor.state!=='open')return null;
  const m=p.message,sender=m.role==='assistant'?m.agent_id:'human:'+m.actor;
  const context={conversation_id:p.room_id,agent:{id:this.config.agent_id,name:this.config.agent_id,is_agent:true},participants:[{id:this.config.agent_id,name:this.config.agent_id,is_agent:true},{id:sender,name:m.actor,is_agent:m.role==='assistant'}],messages:[{id:p.source.id,sender,text:m.text,recipients:m.target_agent_ids}],trigger_id:p.source.id,responsibilities:'Room coordination. Membership and messages confer no Minecraft work authority.'};
  return {context,ids:[p.source.id],sources:[p.source],signature:hash([p.source,p.room_id,context]),occurred_at:p.source.occurredAt,delivery:{eligible:(this.history.data.inbox||[]).length<8,reason_code:(this.history.data.inbox||[]).length<8?null:'inbox_full'}};
 }
 apply(result,inbox){
  const proposal=this.proposal(result.source_id);if(!proposal||proposal.signature!==result.signature||!['engage','hold'].includes(result.action))throw Error('Room participation source changed');
  if(result.action==='engage'&&inbox.length>=8)throw Error('Conversation inbox is full; retry after processing queued messages');
  const before=structuredClone(this.history.data),state=structuredClone(this.state()),p=state.pending.find(p=>p.source.id===result.source_id);
  try{
   if(result.action==='engage')inbox.push({id:p.source.id,source:'huddle',message:p.message.text,username:p.message.actor,room_id:p.room_id,source_fact:p.source,room_actor_kind:p.message.role==='assistant'?'agent':'human',...(result.offer?{attention_offer:result.offer}:{})});
   state.pending=state.pending.filter(row=>row.source.id!==p.source.id);
   state.settled[p.source.id]={reason:result.action,at:Date.now(),source:p.source,room_id:p.room_id};this.commit(state);
  }catch(e){for(const k of Object.keys(this.history.data))delete this.history.data[k];Object.assign(this.history.data,before);inbox.splice(0,inbox.length,...before.inbox);this.history.data.inbox=inbox;throw e;}
  return {queued:result.action==='engage',action:result.action,acp_admitted:false,source_id:p.source.id};
 }
 eligible(message){const row=this.state().rooms[message.room_id],settled=this.state().settled[message.id];return message.source==='huddle'&&row?.membership==='active'&&row.descriptor.state==='open'&&settled?.reason==='engage'&&same(settled.source,message.source_fact)&&!(this.history.data.conversation_admissions||[]).some(r=>r.ids.includes(message.id));}
 stoppedForWork(){return Object.values(this.state().rooms).some(r=>(r.membership==='revoked'||r.descriptor.state==='stopped')&&(associatedWork(this.history,r.descriptor.origin)||this.history.data.turn?.huddle_room_id===r.descriptor.id));}
 async execute(a){
  const {operation,room_id,...args}=a;
  if(operation==='roster')return this.roster();if(operation==='ensure')return this.ensure(args);if(operation==='ensure_status')return this.ensureStatus(a.request_id);if(operation==='discover')return this.sync();
  const id=room_id||this.history.data.turn?.huddle_room_id;if(!id)throw Error('Choose a discovered room_id');const room=this.room(id);
  if(operation==='read')return room.read(a.after??0,a.limit??20);
  if(operation==='status')return room.status(a.request_id);
  if(operation==='return')return room.returnOutcome(a.request_id,a.conversation_revision);
  if(operation==='post')return room.post(args);
  throw Error('Unknown huddle operation');
 }
}
module.exports={AutomaticHuddles,roomSource};
