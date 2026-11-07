const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {WorkshopState}=require('../workshop-state.cjs'),{ActionSequence}=require('../action-sequence.cjs');
function fixture(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'sequence-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));const h=new WorkshopState(path.join(dir,'state.json'));return {h,runner:new ActionSequence(h)};}
const plan={plan_id:'unique-plan',steps:[{tool:'move',arguments:{x:1,y:64,z:0}},{tool:'place',arguments:{x:2,y:64,z:0,item:'oak_planks'}}]};
test('ordered plan executes back to back; lost reply/reload returns evidence without replay',async t=>{
 const {h,runner}=fixture(t),effects=[];
 const opts={guard(){},async execute(step){effects.push(step.tool);return {verified:true};}};
 const result=await runner.run(plan,opts);assert.equal(result.status,'completed');assert.deepEqual(effects,['move','place']);
 const reloaded=new ActionSequence(new WorkshopState(h.file));assert.equal((await reloaded.run(plan,opts)).duplicate,true);assert.equal(effects.length,2);
 await assert.rejects(()=>reloaded.run({...plan,steps:[]},opts),/different sequence/);
});
test('human steering, Stop and authority changes stop pending steps without replaying settled ones',async t=>{
 for(const reason of ['new human input','Stop','expired assignment']){
 const {runner}=fixture(t);let changed=false,effects=0;
 const r=await runner.run(plan,{guard(){if(changed)throw Error(reason);},async execute(){effects++;changed=true;return {verified:true};}});
 assert.equal(r.status,'paused');assert.equal(r.reason,reason);assert.equal(effects,1);assert.equal(r.results.length,1);
 }
});
test('partial, failed and unconfirmed effects stop the plan',async t=>{
 for(const outcome of [{error:'partial build'},{blocked:'terrain changed'},{verified:false},new Error('unknown transfer outcome')]){
 const {runner}=fixture(t);let effects=0;
 const r=await runner.run(plan,{guard(){},async execute(){effects++;if(outcome instanceof Error)throw outcome;return outcome;}});
 assert.equal(r.status,'paused');assert.equal(effects,1);
 }
});
test('cancellation during a running step waits for settlement and excludes concurrent plans',async t=>{
 const {runner}=fixture(t);let release,effects=0;
 const result=runner.run(plan,{guard(){},async execute(){effects++;await new Promise(r=>release=r);return {verified:true};}});
 assert.equal(runner.status().completed,0);assert.equal(runner.cancel().cancel_requested,true);
 await assert.rejects(()=>runner.run({...plan,plan_id:'other'},{guard(){},execute(){}}),/running/);
 release();assert.equal((await result).status,'paused');assert.equal(effects,1);assert.equal(runner.status(),null);
});
test('interrupted receipt and evicted receipt never reopen possibly accepted work',async t=>{
 const {h,runner}=fixture(t);h.data.action_sequences=[{id:plan.plan_id,hash:require('../task-intake.cjs').digest(plan.steps),status:'running',results:[]}];h.save();
 const never={guard(){assert.fail('No fresh admission');},execute(){assert.fail('No replay');}};
 assert.equal((await runner.run(plan,never)).status,'interrupted');
 h.data.action_sequences=[];h.data.consumed_sequence_ids=[require('node:crypto').createHash('sha256').update(plan.plan_id).digest('hex')];h.save();
 await assert.rejects(()=>runner.run(plan,{guard(){},execute:never.execute}),/already consumed/);
});
test('async start returns before effect settlement and exposes exact status without replay',async t=>{
 const {runner}=fixture(t);let release,effects=0;
 const opts={guard(){},async execute(){effects++;await new Promise(r=>release=r);return {verified:true};}};
 const started=await runner.start(plan,opts);assert.equal(started.accepted,true);assert.equal(started.completed,false);assert.equal(effects,1);
 assert.equal(runner.inspect(plan.plan_id).status,'running');assert.equal(runner.inspect(plan.plan_id).results.length,0);
 const duplicate=await runner.start(plan,opts);assert.equal(duplicate.duplicate,true);assert.equal(duplicate.status,'running');assert.equal(effects,1);
 const settled=runner.wait(plan.plan_id,1000);runner.cancel('human correction');release();const receipt=await settled;
 assert.equal(receipt.status,'paused');assert.equal(receipt.results.length,1);assert.equal(effects,1);
 assert.equal((await runner.start(plan,opts)).duplicate,true);assert.equal(effects,1);
});
test('async reservation rejection and interrupted restart never claim acceptance or replay',async t=>{
 const {runner,h}=fixture(t);await assert.rejects(()=>runner.start(plan,{guard(){throw Error('expired');},execute(){assert.fail();}}),/expired/);
 assert.equal(runner.inspect(plan.plan_id).status,'unknown');
 let release;await runner.start(plan,{guard(){},execute(){return new Promise(r=>release=r);}});
 const loaded=new ActionSequence(new WorkshopState(h.file));assert.equal(loaded.inspect(plan.plan_id).status,'interrupted');
 const r=await loaded.start(plan,{guard(){assert.fail();},execute(){assert.fail();}});assert.equal(r.accepted,false);assert.equal(r.replayed,false);
 runner.cancel();release({verified:true});await runner.wait(plan.plan_id,1000);
});
