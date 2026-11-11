// Packetize one completed utterance, never infer ACP completion from punctuation.
function packets(text,prefix='',width=240){
 const clean=String(text).replace(/[\r\n\x00-\x1f]/g,' ').trim();
 if(!clean||clean.startsWith('/')||clean.length>4000)throw Error('Use 1–4000 characters of ordinary chat');
 const available=width-prefix.length;if(available<40)throw Error('Address is too long');
 let remaining=clean;const result=[];
 while(remaining){
  let part=remaining.slice(0,available);
  // Java's chat length is UTF-16; do not split a surrogate pair.
  if(/[\uD800-\uDBFF]$/.test(part))part=part.slice(0,-1);
  if(part.length<remaining.length){
   const endings=[...part.matchAll(/[.!?…]["'”’)]*(?=\s|$)/g)];
   if(endings.length){const last=endings.at(-1);part=part.slice(0,last.index+last[0].length);}
   else if(part.includes(' '))part=part.slice(0,part.lastIndexOf(' '));
  }
  result.push(prefix+part);remaining=remaining.slice(part.length).trimStart();
 }
 return result;
}
const {publicSource}=require('./source-revision.cjs');
function sameSource(a,b){return a&&b&&a.id===b.id&&a.revision===b.revision&&a.occurredAt===b.occurredAt;}
function pendingSource(data,source){
 const message=data.inbox?.find(m=>m.id===source.id&&m.source==='human'&&!m.whisper&&!m.attention_offer);
 const event=data.events.find(e=>e.id===source.id&&e.source==='human'&&e.accepted===true);
 return message&&sameSource(publicSource(event),source)?event:null;
}
function replySources(data,requested,conversation){
 if(requested===undefined)return [];
 if(!Array.isArray(requested)||!requested.length||requested.length>8||new Set(requested.map(s=>s?.id)).size!==requested.length)throw Error('Choose distinct pending public human sources for this response');
 if(data.turn?.reply_recipient||data.turn?.reply_route)throw Error('A private response cannot settle public input');
 for(const source of requested){
  if(!source||typeof source.id!=='string'||typeof source.revision!=='string'||!Number.isSafeInteger(source.occurredAt)||!conversation.wasExposed(source)||!pendingSource(data,source))throw Error('Reply source changed or was not exposed as pending public input; read conversation first');
 }
 return requested.map(s=>({id:s.id,revision:s.revision,occurredAt:s.occurredAt}));
}
// A server-attributed self echo confirms submission on this server, not that
// every recipient read the message. Ambiguous/absent echoes do not settle input.
function confirmEcho(data,text,transport,username,at){
 if(transport?.kind!=='server_player_uuid'||transport.username!==username)return false;
 const candidates=(data.turn?.speech_operations||[]).flatMap(o=>o.reply_to?.length||o.huddle_return?o.packets:[])
  .filter(p=>['submitting','submitted'].includes(p.status)&&p.text===text&&!p.server_echo);
 if(candidates.length!==1)return false;
 candidates[0].server_echo={at,transport:{...transport}};return true;
}
function settleReplies(data,{error=false,budgetLimited=false,at=new Date().toISOString()}={}){
 const turn=data.turn;
 if(!turn||error||budgetLimited||turn.actions?.some(a=>a.status!=='succeeded'))return;
 const receipts=data.input_outcomes||(data.input_outcomes=[]);
 for(const op of turn.speech_operations||[]){
  if(op.status!=='submitted'||!op.reply_to?.length||!op.packets.length||op.packets.some(p=>p.status!=='submitted'||!p.server_echo))continue;
  for(const source of op.reply_to){
   if(!pendingSource(data,source)||receipts.some(r=>r.request_id===source.id))continue;
   receipts.push({request_id:source.id,delivery:'terminal',admitted_at:null,terminal_at:at,
    reason:'responded_during_active_turn',conversation_only:turn.conversation_only===true,turn_task_id:turn.task_id||null,
    source_ids:[source.id],source_fact:source,operation_id:op.id,
    responses:op.packets.map((p,i)=>({id:op.id+':'+i,at:p.server_echo.at,text:p.text,audience:'public'})),
    task_authorizations:[],completion:'not_established'});
   const index=data.inbox.findIndex(m=>m.id===source.id);data.inbox.splice(index,1);
  }
 }
 data.input_outcomes=receipts.slice(-500);
}
module.exports={packets,replySources,confirmEcho,settleReplies};
