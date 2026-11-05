const test=require('node:test'),assert=require('node:assert/strict');
const {taskView,worldView}=require('../planner-view.cjs');
const {EventEmitter}=require('node:events'),{Readable}=require('node:stream');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {createRequire}=require('node:module');
const root=path.resolve(__dirname,'..'),realRequire=createRequire(path.join(root,'body.cjs'));
const clone=x=>JSON.parse(JSON.stringify(x));
function task(){return {id:'same-task',request_id:'owner-request',request:'Preserve the harbor; stop at the authorized deadline.',
 status:'running',turns:38,max_turns:135,deadline:Date.now()+3600000,reviewers:['Peer'],wait_for:null,
 recovery_attempts:2,progress_revision:30,unknown_receipt:'still-unknown',
 progress:Array.from({length:30},(_,i)=>({at:'time-'+i,summary:'Reported step '+i,
  observation:{recent_actions:[{result:{samples:'nested-old-observation '.repeat(250)}}]}})),
 last_observed:{at:'last',position:{x:3,y:64,z:1},health:20,recent_actions:[{result:'complete old detail'}]}};}
test('recent view preserves authority, uncertainty and exact current facts without modifying evidence',()=>{
 const source={task:task(),position:{x:1,y:64,z:2},inventory:[{name:'stone',count:3}],
  conversation:{revision:'current',messages:[{text:'Changed plan'}]},remaining_actions:8,
  events:[{kind:'chat',id:'owner-request',source:'human',provenance:'operator_control',message:'Existing authorization'},
   {kind:'work_status',progress:{summary:'Checkpoint',observation:{recent_actions:['old']}},status:'needs_review'},
   {kind:'action_failed',error:'Unconfirmed removal',operation_settled:false,timeout:true,arguments:{x:3}},
   {kind:'action_result',result:{error:'Pickup unknown',inventory:[1,2,3]}}],
  receipts:Array.from({length:15},(_,i)=>({id:i,result:{error:i===14?'Pickup unknown':null,confirmed:false}}))};
 const saved=clone(source),view=worldView(source);
 assert.deepEqual(source,saved);
 for(const key of ['id','request_id','request','deadline','max_turns','turns','status','reviewers','recovery_attempts','unknown_receipt'])assert.deepEqual(view.task[key],source.task[key]);
 for(const key of ['position','inventory','conversation','remaining_actions'])assert.deepEqual(view[key],source[key]);
 assert.equal(view.task.progress.length,5);assert.equal(view.task.progress[0].summary,'Reported step 25');
 assert.equal(view.task.history_view.retained_progress,30);assert.equal(view.task.progress[0].observation_omitted,true);
 assert.equal(view.task.last_observed.recent_action_count,1);assert.equal(view.task.last_observed.action_details_omitted,true);
 assert.deepEqual(view.events[0],source.events[0]);assert.equal(view.events[1].progress.observation,undefined);
 assert.equal(view.events[2].error,'Unconfirmed removal');assert.equal(view.events[2].operation_settled,false);
 assert.equal(view.events[3].error,'Pickup unknown');assert.equal(view.events[3].result_details_omitted,true);
 assert.deepEqual(view.receipts,source.receipts.slice(-5));
 assert.ok(JSON.stringify(view).length<JSON.stringify(source).length/5,'Repeated nested receipts must not flood the planner');
});
test('unavailable state and stopped/exhausted/review tasks never acquire runnable authority',()=>{
 assert.equal(taskView(null),null);assert.equal(worldView({ready:false}).ready,false);
 for(const status of ['stopped','budget_exhausted','needs_review']){
  const value=task();value.status=status;value.deadline=1;
  const view=taskView(value);assert.equal(view.status,status);assert.equal(view.deadline,1);assert.equal(view.turns,38);
 }
});
function bodyFixture(){
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'planner-view-')),file=path.join(home,'workshop.json'),cfg=path.join(home,'config.json');
 const initial={task:task(),turn:null,events:[]};fs.writeFileSync(file,JSON.stringify(initial));fs.writeFileSync(cfg,JSON.stringify({username:'Builder',token:'fixture'}));
 const {Vec3}=realRequire('vec3'),bot=new EventEmitter();
 Object.assign(bot,{username:'Builder',entity:{position:new Vec3(1,64,2)},players:{},health:20,food:20,time:{timeOfDay:6000},
  loadPlugin(){},inventory:{items:()=>[{name:'stone',count:3}]},findBlocks:()=>[]});
 let handle;
 const ctx=vm.createContext({require:n=>n==='mineflayer'?{createBot:()=>bot}:n==='node:http'?{createServer:h=>{handle=h;return {listen(){},close(){}};}}:
  n==='./spatial.cjs'?{...realRequire(n),localMap:()=>({slices:[]})}:realRequire(n),
  module:{exports:{}},console:{log(){}},Buffer,process:{argv:['node','body.cjs',cfg],on(){},exit(){assert.fail('Unexpected exit');}},setTimeout,clearTimeout});
 vm.runInContext(fs.readFileSync(path.join(root,'body.cjs'),'utf8')+'\nready=true;module.exports={operate,history,start(){history.startTurn();turnUntil=Date.now()+240000;}};',ctx);
 return {...ctx.module.exports,file,initial,async request(url,authorization='Bearer fixture'){
  const req=Readable.from([]);Object.assign(req,{url,method:'GET',headers:{authorization}});let status,text;
  await handle(req,{writeHead:x=>status=x,end:x=>text=x});return {status,value:text?JSON.parse(text):null};
 },close:()=>fs.rmSync(home,{recursive:true,force:true})};
}
test('actual body provides compact and explicit full observations under the same authentication',async()=>{
 const f=bodyFixture();try{
  const before=fs.readFileSync(f.file,'utf8');
  const summary=await f.request('/observation'),full=await f.request('/state');
  assert.equal(summary.status,200);assert.equal(summary.value.task.progress.length,5);assert.equal(full.value.task.progress.length,30);
  assert.equal((await f.request('/observation','Bearer wrong')).status,401);
  assert.equal((await f.operate('observe')).task.progress.length,5);
  const detailed=await f.operate('observe',{detail:'full'});
  assert.deepEqual(clone(detailed.task),f.initial.task);assert.equal(fs.readFileSync(f.file,'utf8'),before);
 }finally{f.close();}
});
test('work report and note return recent progress while durable observations remain complete',async()=>{
 const f=bodyFixture();try{
  f.start();const report=await f.operate('work_report',{status:'running',summary:'Roof still unfinished'});
  assert.equal(report.progress.length,5);assert.equal(report.progress.at(-1).summary,'Roof still unfinished');
  const note=await f.operate('work_note',{task_id:'same-task',summary:'Reviewed action effects, still unknown input'});
  assert.equal(note.progress.length,5);assert.equal(note.progress.at(-1).observation_omitted,true);
  const saved=JSON.parse(fs.readFileSync(f.file,'utf8'));
  assert.equal(saved.task.progress.length,30);assert.ok(saved.task.progress[0].observation.recent_actions.length);
  assert.equal(saved.task.progress.at(-1).observation.position.y,64);
  assert.equal(saved.task.deadline,f.initial.task.deadline);assert.equal(saved.task.max_turns,135);
  assert.equal(saved.task.turns,39);assert.equal(saved.task.unknown_receipt,'still-unknown');
 }finally{f.close();}
});
