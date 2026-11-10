const test=require('node:test'),assert=require('node:assert/strict');
const {HuddleJournal,publicReturnSource}=require('../huddle-journal.cjs');
const {publicSource}=require('../source-revision.cjs');
const binding={host:'https://room.test',room_id:'room',agent_id:'agent',connection_id:'game'};
const id='d68c0154-aea4-40a9-b4b7-83233ed02de9';
function fixture(){let disk;const history={data:{task:{id:'old',status:'budget_exhausted',turns:8},inbox:[],events:[],activity_stop:{at:1}},save(){disk=JSON.stringify(this.data);}};history.save();return {history,reload:()=>({data:JSON.parse(disk),save:history.save})};}
test('post intent precedes transport; lost acknowledgment/restart permits status only',()=>{
 const f=fixture(),j=new HuddleJournal(f.history,binding),payload={request_id:id,text:'Coordination',target_agent_ids:[],kind:'message'};
 assert.equal(j.begin(payload).send,true);assert.equal(j.read(id).state,'unknown');
 const h=f.reload(),again=new HuddleJournal(h,binding);assert.equal(again.begin(payload).send,false);
 assert.equal(again.read(id).state,'unknown');assert.throws(()=>again.begin({...payload,text:'Changed'}),/different payload/);
 assert.deepEqual(h.data.task,{id:'old',status:'budget_exhausted',turns:8});assert.deepEqual(h.data.inbox,[]);assert.deepEqual(h.data.events,[]);assert.deepEqual(h.data.activity_stop,{at:1});
});
test('only the original participant journal sees its operation',()=>{
 const {history}=fixture(),j=new HuddleJournal(history,binding);j.begin({request_id:id});
 for(const k of Object.keys(binding))assert.equal(new HuddleJournal(history,{...binding,[k]:'different'}).read(id).started_at,undefined);
});
test('save failures roll back memory and cannot authorize sending or fabricate saved receipt',()=>{
 const f=fixture(),j=new HuddleJournal(f.history,binding),before=JSON.stringify(f.history.data),save=f.history.save;
 f.history.save=()=>{throw Error('disk');};assert.throws(()=>j.begin({request_id:id}),/disk/);assert.equal(JSON.stringify(f.history.data),before);
 f.history.save=save;j.begin({request_id:id});f.history.save=()=>{throw Error('disk');};assert.throws(()=>j.saved(id,{state:'saved'}),/disk/);assert.equal(j.read(id).state,'unknown');
});
test('saved receipt is immutable and never a work completion assertion',()=>{
 const {history}=fixture(),j=new HuddleJournal(history,binding);j.begin({request_id:id});
 const r=j.saved(id,{state:'saved',message_id:'m'});assert.equal(r.completion,undefined);
 assert.deepEqual(j.saved(id,r.receipt),r);assert.throws(()=>j.saved(id,{state:'saved',message_id:'other'}),/changed/);
 assert.equal(j.begin({request_id:id}).send,false);
});
function originFixture(){
 const {history}=fixture(),event={id:'human-source',time:'2026-11-10T12:00:00.000Z',kind:'chat',source:'human',accepted:true,username:'Human',message:'Please coordinate',provenance:'minecraft_public_chat',transport:{kind:'server_player_uuid',uuid:'human-uuid',username:'Human'}};
 history.data.events.push(event);
 const origin={kind:'external',service:'minecraft',connection_id:'game',conversation_id:'game-public',request_id:id,source_id:event.id,source_revision:publicSource(event).revision,occurred_at:Date.parse(event.time),actor:{id:'human-uuid',kind:'human'}};
 return {history,event,origin,enrollment:{...binding,origin:structuredClone(origin)}};
}
test('return matches original public human source without completing, admitting or renewing work',()=>{
 const f=originFixture(),before=JSON.stringify(f.history.data),r=publicReturnSource(f.history,f.enrollment,f.origin);
 assert.equal(r.source_fact.id,'human-source');assert.equal(r.audience,'minecraft_public_chat');assert.equal(JSON.stringify(f.history.data),before);
});
test('an original requested result may use retained old evidence without freshening its time',()=>{
 const f=originFixture();f.history.data.public_conversation_history=f.history.data.events;f.history.data.events=[];
 const r=publicReturnSource(f.history,f.enrollment,f.origin);assert.equal(r.source_fact.occurredAt,f.origin.occurred_at);
});
test('viewer, peer, private, foreign, edited and missing sources cannot choose public destination',()=>{
 const f=originFixture();
 for(const change of [{connection_id:'other'},{kind:'conversation'},{service:'companion'},{actor:{id:'viewer'}},{source_revision:'changed'},{occurred_at:'2026-11-10T13:00:00.000Z'}])assert.throws(()=>publicReturnSource(f.history,f.enrollment,{...f.origin,...change}));
 for(const change of [{source:'agent'},{whisper:true},{provenance:'operator_control'},{accepted:false},{message:'Changed'},{transport:{kind:'unverified'}}]){const g=originFixture();Object.assign(g.event,change);assert.throws(()=>publicReturnSource(g.history,g.enrollment,g.origin));}
 f.history.data.events=[];assert.throws(()=>publicReturnSource(f.history,f.enrollment,f.origin));
});
