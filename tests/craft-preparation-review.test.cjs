const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {WorkshopState}=require('../workshop-state.cjs');
const {review}=require('../activity-review.cjs'),policy=require('../activity-policy.cjs');
const digest=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex');
const cfg={human_engagement:{enabled:true,task_optional:true}};
const terminal='No recipe possible with current inventory and nearby crafting table; no movement performed';
function fixture(t){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'craft-review-'));t.after(()=>fs.rmSync(home,{recursive:true,force:true}));
 const h=new WorkshopState(path.join(home,'workshop.json'));
 h.data.task={id:'unchanged',status:'blocked',turns:23,deadline:null,max_turns:null};
 h.data.input_outcomes=[{input_id:'old-input',state:'notAccepted'}];
 h.data.last_turn={activity:true,task_id:null,interrupted:false,budget_limited:true,started_at:'2026-11-12T20:04:40.276Z',actions:[{id:'first',status:'uncertain'},{id:'second',status:'uncertain'}]};
 for(const id of ['first','second'])for(const kind of ['action_started','action_failed'])h.data.events.push({id:crypto.randomUUID(),action_id:id,kind,action:'craft',arguments:{item:'stone_pickaxe',count:1},time:'2026-11-12T20:05:18.380Z',...(kind==='action_failed'?{error:terminal}:{})});
 const observation={position:{x:1.5,y:63,z:1.5},inventory:{slots:Array(46).fill(null),cursor:null}};
 // A present item is a current fact, never proof of either historical craft.
 observation.inventory.slots[9]={name:'stone_pickaxe',count:1};
 const input={generation:7,request_id:crypto.randomUUID(),expected_turn_sha256:digest(h.data.last_turn),expected_position:structuredClone(observation.position),expected_inventory_sha256:digest(observation.inventory),evidence_sha256:'a'.repeat(64),reviews:['first','second'].map(id=>({action_id:id,receipt_sha256:digest(h.data.events.find(e=>e.action_id===id&&e.kind==='action_failed')),outcome:'settled_failed_crafting_preparation',reason:'Exact retained source and terminal reviewed; preparation completed, but historical inventory deltas remain unclaimed.'}))};
 h.save();return {h,input,observation};
}
test('review preserves both uncertain crafts, inputs and task; no old continuation, repeat or fabricated delta',t=>{
 const {h,input,observation}=fixture(t),before=structuredClone(h.data);
 assert.equal(policy.reason(h,cfg),'unresolved_activity_effects');
 const result=review(h,cfg,input,observation);
 assert.equal(result.activity_allowed,true);assert.equal(result.future_work_only,true);assert.equal(result.replayed,false);
 assert.equal(policy.canContinue(h,cfg),false);
 for(const field of ['task','events','input_outcomes'])assert.deepEqual(h.data[field],before[field]);
 const original=structuredClone(h.data.last_turn);delete original.effect_review;
 for(const a of original.actions){assert.equal(a.status,'uncertain');delete a.review;}
 assert.deepEqual(original,before.last_turn);
 const reloaded=new WorkshopState(h.file),saved=JSON.stringify(reloaded.data);
 assert.equal(review(reloaded,cfg,input,observation).duplicate,true);
 assert.equal(JSON.stringify(reloaded.data),saved);assert.equal(policy.canContinue(reloaded,cfg),false);
 assert.throws(()=>review(reloaded,cfg,{...input,request_id:crypto.randomUUID()},observation));
});
for(const mode of ['no_effect','other_outcome','other_action','timeout','unsettled','partial_recipe','preparation_timeout','new_terminal','unknown_item','bad_count','extra_argument','cursor','output','grid','unknown_cursor','unknown_grid','missing_second','pending','interrupted','task_turn','active','missing_terminal','duplicate_terminal','stale_position','stale_inventory'])test('craft review refuses '+mode+' without mutation',t=>{
 const {h,input,observation}=fixture(t),first=h.data.events.find(e=>e.action_id==='first'&&e.kind==='action_failed');
 if(mode==='no_effect')input.reviews[0].outcome='no_effect';
 if(mode==='other_outcome')input.reviews[0].outcome='settled_failed_storage';
 if(mode==='other_action')for(const e of h.data.events.filter(e=>e.action_id==='first'))e.action='move';
 if(mode==='timeout')first.timeout=true;
 if(mode==='unsettled')first.operation_settled=false;
 if(mode==='partial_recipe')first.error='No recipe possible with current server inventory; 1 recipe executions completed. Inventory/crafting grid may contain partial work; inspect before retrying.';
 if(mode==='preparation_timeout')first.error='Server did not confirm inventory synchronization';
 if(mode==='new_terminal')first.error='No recipe possible after crafting preparation; cursor/grid contents or window state may have changed. Inspect inventory and crafting state before retrying; no movement performed';
 if(['unknown_item','bad_count','extra_argument'].includes(mode))for(const e of h.data.events.filter(e=>e.action_id==='first')){
  if(mode==='unknown_item')e.arguments.item='';
  if(mode==='bad_count')e.arguments.count=9;
  if(mode==='extra_argument')e.arguments.other='unreviewed';
 }
 if(mode==='cursor')observation.inventory.cursor={name:'dirt',count:1};
 if(mode==='output')observation.inventory.slots[0]={name:'stick',count:4};
 if(mode==='grid')observation.inventory.slots[1]={name:'dirt',count:1};
 if(mode==='unknown_cursor')delete observation.inventory.cursor;
 if(mode==='unknown_grid')delete observation.inventory.slots[2];
 if(mode==='missing_second')input.reviews.pop();
 if(mode==='pending')h.data.last_turn.actions[1].status='pending';
 if(mode==='interrupted')h.data.last_turn.interrupted=true;
 if(mode==='task_turn')h.data.last_turn.task_id='unchanged';
 if(mode==='active')h.data.turn={activity:true};
 if(mode==='missing_terminal')h.data.events=h.data.events.filter(e=>e!==first);
 if(mode==='duplicate_terminal')h.data.events.push({...first,id:crypto.randomUUID()});
 if(mode==='stale_position')observation.position.x++;
 if(mode==='stale_inventory')observation.inventory.slots[9]=null;
 input.expected_turn_sha256=digest(h.data.last_turn);input.reviews[0].receipt_sha256=digest(first);
 if(mode!=='stale_inventory')input.expected_inventory_sha256=digest(observation.inventory);
 const before=JSON.stringify(h.data);assert.throws(()=>review(h,cfg,input,observation));assert.equal(JSON.stringify(h.data),before);
});
test('explicit Stop remains authoritative after a settled preparation review',t=>{
 const {h,input,observation}=fixture(t);h.data.activity_stop={at:1,reason:'Stop'};const stop=structuredClone(h.data.activity_stop);
 const result=review(h,cfg,input,observation);assert.equal(result.activity_allowed,false);assert.equal(result.blocked_reason,'explicit_stop');
 assert.deepEqual(h.data.activity_stop,stop);assert.equal(policy.canContinue(h,cfg),false);
});
test('failed save retains both original uncertain actions and hold',t=>{
 const {h,input,observation}=fixture(t),before=JSON.stringify(h.data),disk=fs.readFileSync(h.file,'utf8');
 h.save=()=>{throw Error('disk full');};assert.throws(()=>review(h,cfg,input,observation),/disk full/);
 assert.equal(JSON.stringify(h.data),before);assert.equal(fs.readFileSync(h.file,'utf8'),disk);assert.equal(policy.reason(h,cfg),'unresolved_activity_effects');
});
