// Minecraft evidence projection only. Watch policy and persistence live in Rust.
const fs=require('node:fs');
const path=require('node:path');
const {execFile}=require('node:child_process');
const {promisify}=require('node:util');
const exec=promisify(execFile);
const bounds=require('./task-bounds.cjs');
const helpers=require('./helper-capabilities.cjs');
const {isPublicChatEvent}=require('./public-chat.cjs');

function bounded(value,limit=1400){const text=JSON.stringify(value);return text.length<=limit?value:{truncated:true,excerpt:text.slice(0,limit)};}
function messageEnvelope(cfg,e){
 // tell's first @addressee and visible FYI/ACK marker are game transport facts.
 // A later mention, a quoted address, or a name embedded in prose is not a recipient.
 const first=(e.message||e.sent||'').match(/^@([A-Za-z0-9_]{1,16})\s+(?:\[(FYI|ACK)\]\s+)?/i);
 const canonical=name=>[cfg.username,...(cfg.bot_names||[])].find(n=>n.toLowerCase()===name.toLowerCase())||
  Object.keys(cfg.aliases||{}).find(n=>(cfg.aliases[n]||[]).some(a=>a.toLowerCase()===name.toLowerCase()))||name;
 return {author:e.username||cfg.username,recipients:first?[canonical(first[1])]:[],
  intent:first?first[2]?.toUpperCase()==='FYI'?'update':first[2]?.toUpperCase()==='ACK'?'ack':'request':null};
}
function context(cfg,history,live){
 const task=history.task();const since=task?.started_at||'';
 const records=history.data.events.filter(e=>!e.whisper&&e.time>=since);
 const messages=records.filter(isPublicChatEvent).slice(-30);
 const actions=records.filter(e=>['action_result','action_failed'].includes(e.kind)).slice(-10);
 const events=[...messages.map(e=>({id:e.id,kind:'message',source:`Public ${e.source||'self'} report: ${e.username||cfg.username}`,content:bounded({time:e.time,text:e.message||e.sent}),message:messageEnvelope(cfg,e)})),
  ...actions.map(e=>({id:e.id,kind:'tool',source:'Local game tool receipt',content:bounded(e)}))];
 if(live.ready){
  const inventory_counts={};for(const item of live.inventory||[])inventory_counts[item.name]=(inventory_counts[item.name]||0)+item.count;
  const position=p=>p?Object.fromEntries(Object.entries(p).map(([k,v])=>[k,Math.floor(v)])):null;
  events.push({id:'environment:self',kind:'environment',source:'Direct current player observation',content:{position:position(live.position),health:live.health,inventory:live.inventory,inventory_counts}});
  events.push({id:'environment:peers',kind:'environment',source:'Visible game players',content:(live.players||[]).map(p=>({name:p.name,position:position(p.position)}))});
  if(live.crops)events.push({id:'environment:crops',kind:'environment',source:'Loaded nearby crop and farmland block states',content:{...live.crops,by_position:Object.fromEntries((live.crops.blocks||[]).filter(b=>b.position&&['x','y','z'].every(k=>Number.isInteger(b.position[k]))).map(b=>[[b.position.x,b.position.y,b.position.z].join(','),b]))}});
 }
 return {scope:`${cfg.conversation_id||'minecraft:workshop'}:${cfg.username}`,
  task:task?{id:task.id,goal:task.goal,status:task.status,deadline_ms:task.bounds?bounds.get(task).deadline_ms:task.deadline,remaining_turns:task.bounds?bounds.remaining(task).remaining_turns:Math.max(0,task.max_turns-task.turns)}:null,events};
}

async function invoke(command,home,input,operation='watch'){
 const tagged=operation==='watch'?input.task?.deadline_ms&&typeof input.task.deadline_ms==='object':input.remaining_ms&&typeof input.remaining_ms==='object';
 const capabilities=await helpers.discover(command);
 if(tagged&&!helpers.supports(capabilities,operation))throw Error(`Local ${operation}-v2 support is unavailable; no bound conversion or authority renewal`);
 const subcommand=tagged?`${operation}-v2`:operation;
 const temp=fs.mkdtempSync(path.join(home,'watch-request-'));
 try{
  const file=path.join(temp,'input.json');fs.writeFileSync(file,JSON.stringify(input),{mode:0o600});
  const {stdout}=await exec(command,operation==='watch'?[subcommand,'--store',path.join(home,'watches.json'),file]:[subcommand,file],{timeout:5000,maxBuffer:512*1024});
  return JSON.parse(stdout);
 }catch(e){throw Error(e.stderr?.trim().slice(0,400)||'Attention watch operation failed');}
 finally{fs.rmSync(temp,{recursive:true,force:true});}
}
module.exports={context,invoke,messageEnvelope};
