const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {WorldToolsState}=require('../world-tools-state.cjs');
function fixture(t,legacy={}) {
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'world-receipt-'));
 const file=path.join(home,'workshop.json'),original=JSON.stringify(legacy);
 fs.writeFileSync(file,original);
 t.after(()=>{assert.equal(fs.readFileSync(file,'utf8'),original);fs.rmSync(home,{recursive:true,force:true});});
 return {home,store:new WorldToolsState(home)};
}
test('a lost dispatch survives restart and cannot be repeated through another tool or new id',t=>{
 const {home,store}=fixture(t);
 store.begin('dig',{operation_id:'intent-001',x:1,y:2,z:3});
 const restored=new WorldToolsState(home);
 assert.equal(restored.begin('dig',{operation_id:'intent-001',z:3,y:2,x:1}).prior.status,'started');
 assert.throws(()=>restored.begin('gather',{operation_id:'intent-002',targets:[{x:1,y:2,z:3}]}),/uncertain/);
 assert.throws(()=>restored.begin('dig',{operation_id:'intent-001',x:4,y:2,z:3}),/different/);
 assert.ok(restored.begin('chat',{text:'Checking terrain',operation_id:'speech-001'}).entry);
});
test('legacy unknown id and original Stop persist; old queued inputs cannot dispatch',t=>{
 const {store}=fixture(t,{activity_stop:{at:123},turn:{actions:[{id:'earlier',status:'uncertain'}]},inbox:[{id:'old'}]});
 assert.deepEqual(store.data.public_inbox,[]);assert.equal(store.data.stopped.at,123);
 assert.throws(()=>store.begin('move',{operation_id:'newmove-001',x:2}),/Historical/);
});
test('atomic public acknowledgement consumes only its exact head across restart',t=>{
 const {store,home}=fixture(t);
 const a=store.record('chat',{message:'hello'},true),b=store.record('chat',{message:'next'},true);
 assert.throws(()=>store.acknowledge(b.id),/head/);store.acknowledge(a.id);
 const next=new WorldToolsState(home);assert.equal(next.data.public_inbox[0].id,b.id);
 assert.throws(()=>next.acknowledge(a.id),/head/);
});
test('an existing exact no-effect review remains valid for fresh work only',t=>{
 const turn={activity:true,actions:[{id:'legacy-action-1',status:'uncertain'}]};
 const original=require('node:crypto').createHash('sha256').update(JSON.stringify(turn)).digest('hex');
 turn.actions[0].review={outcome:'no_effect',original_turn_sha256:original};
 const {store}=fixture(t,{last_turn:turn});
 assert.ok(store.begin('move',{operation_id:'new-intent-001'}).entry);
 assert.throws(()=>store.begin('move',{operation_id:'legacy-action-1'}));
 store.legacy.last_turn.actions[0].review.original_turn_sha256='wrong';
 assert.throws(()=>store.begin('chat',{operation_id:'fresh-chat-001'}),/Historical action/);
});
test('a lost dig conflicts with aliases on its block and permits independent targets',t=>{
 const {store}=fixture(t);
 store.begin('dig',{x:1,y:65,z:2,expected:'stone',operation_id:'lost-dig-1'});
 assert.throws(()=>store.begin('place',{x:1,y:65,z:2,item:'dirt',operation_id:'other-id-1'}),/overlapping/);
 assert.throws(()=>store.begin('gather',{block:'stone',targets:[{x:1,y:65,z:2}],operation_id:'other-id-2'}),/overlapping/);
 assert.ok(store.begin('dig',{x:12,y:65,z:2,expected:'stone',operation_id:'real-dig-2'}).entry);
 assert.ok(store.begin('container',{x:5,y:65,z:2,expected:'chest',operation_id:'container-11'}).entry);
 assert.ok(store.begin('move',{x:9,y:65,z:2,operation_id:'walk-111'}).entry);
});
test('entity identity survives an altered numeric id and an independent target can proceed',t=>{
 const {store}=fixture(t);
 store.begin('attack',{id:1,uuid:'a',operation_id:'attack-111'});
 assert.throws(()=>store.begin('shear',{id:99,uuid:'a',operation_id:'shear-222'}),/overlapping/);
 assert.ok(store.begin('attack',{id:1,uuid:'b',operation_id:'attack-333'}).entry);
});

test('a partially executed legacy craft survives journal rotation and restart',t=>{
 const id='legacy-partial-craft';
 const args={item:'stick',count:4};
 const events=[
  {id:'start-receipt',kind:'action_started',action_id:id,action:'craft',arguments:args},
  {id:'failure-receipt',kind:'action_failed',action_id:id,action:'craft',arguments:args,error:'Insufficient ingredients after 2 completed recipe executions'}
 ];
 const turn={actions:[{id,status:'uncertain'}]};
 const {home}=fixture(t,{last_turn:turn,events:[]});
 const journal=path.join(home,'workshop.json');
 const rotated=fs.readFileSync(journal);
 fs.writeFileSync(journal,JSON.stringify({last_turn:turn,events}));
 new WorldToolsState(home);
 fs.writeFileSync(journal,rotated);
 const store=new WorldToolsState(home);
 assert.deepEqual(JSON.parse(fs.readFileSync(path.join(home,'world-tools/legacy-action-evidence.json'))),events);
 store.data.events=Array.from({length:2000},(_,n)=>({kind:'chat',id:'chat-'+n}));
 store.record('world_ready',{});
 const reloaded=new WorldToolsState(home);
 assert.ok(reloaded.begin('equip',{operation_id:'equip-redstone',item:'redstone'}).entry);
 assert.ok(reloaded.begin('chat',{operation_id:'report-redstone',text:'Holding redstone.'}).entry);
 assert.throws(()=>reloaded.begin('craft',{operation_id:id,...args}),/historical work/);
 assert.throws(()=>reloaded.begin('craft',{operation_id:'different-craft-id',...args}),/Historical action/);
 assert.throws(()=>reloaded.begin('move',{operation_id:'different-move-id'}),/Historical action/);
 assert.deepEqual(reloaded.legacy.last_turn,turn);
 fs.writeFileSync(journal,JSON.stringify({events:[]}));
 try {
  const withoutTurn=new WorldToolsState(home);
  assert.throws(()=>withoutTurn.begin('craft',{operation_id:id,...args}),/historical work/);
  assert.throws(()=>withoutTurn.begin('craft',{operation_id:'new-id-after-turn',...args}),/Historical action/);
 } finally { fs.writeFileSync(journal,rotated); }
});

test('a new uncertain craft retains its arguments and partial result after event rollover',t=>{
 const {home,store}=fixture(t);
 const args={operation_id:'fresh-craft-id',item:'stick',count:4};
 const {entry}=store.begin('craft',args);
 const result={error:'Partial recipe execution'};
 store.finish(entry,'unknown',result);
 store.data.events=Array.from({length:2000},(_,n)=>({kind:'chat',id:'chat-'+n}));
 store.record('world_ready',{});
 const restarted=new WorldToolsState(home);
 const receipt=restarted.begin('craft',args).prior;
 assert.deepEqual(receipt.arguments,{item:'stick',count:4});
 assert.deepEqual(receipt.result,result);
 assert.equal(receipt.status,'unknown');
 assert.throws(()=>restarted.begin('craft',{...args,operation_id:'another-craft-id'}),/overlapping/);
 assert.ok(restarted.begin('equip',{operation_id:'fresh-redstone',item:'redstone'}).entry);
});

test('inconsistent or terminal-only historical evidence cannot narrow an unknown',t=>{
 const id='legacy-unknown-action';
 const turn={actions:[{id,status:'uncertain'}]};
 const failure={kind:'action_failed',action_id:id,action:'craft',arguments:{item:'stick',count:4}};
 for(const starts of [[],[{kind:'action_started',action_id:id,action:'equip',arguments:{item:'redstone'}}]]) {
  const {home}=fixture(t,{last_turn:turn,events:[...starts,failure]});
  const store=new WorldToolsState(home);
  assert.throws(()=>store.begin('chat',{operation_id:'original-report',text:'Checking'}),/Historical action/);
  assert.throws(()=>store.begin('craft',{operation_id:id,item:'stick',count:4}),/historical work/);
 }
});
