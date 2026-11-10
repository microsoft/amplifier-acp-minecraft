const test=require('node:test'),assert=require('node:assert/strict');
const {packets}=require('../speech.cjs');
test('completed speech preserves every word and address within UTF-16 wire length',()=>{
 const text=('Look at this landing 😀. '+'Another useful observation with detail. ').repeat(25),prefix='@Builder [FYI] ';
 const chunks=packets(text,prefix);
 assert.ok(chunks.length>1);assert.ok(chunks.every(c=>c.length<=240&&c.startsWith(prefix)&&!/[\uD800-\uDBFF]$/.test(c)));
 assert.equal(chunks.map(c=>c.slice(prefix.length)).join(' '),text.trim());
});
test('commands, empty and oversized utterances reject before any transport',()=>{
 for(const t of ['/kill','', 'x'.repeat(4001)])assert.throws(()=>packets(t));
});
test('partial, ambiguous and unconfirmed speech packets preserve pending source',()=>{
 const {confirmEcho,settleReplies}=require('../speech.cjs'),{publicSource}=require('../source-revision.cjs');
 const e={id:'human',kind:'chat',source:'human',username:'Visitor',message:'Question',accepted:true,provenance:'minecraft_public_chat',time:new Date().toISOString()};
 for(const variant of ['partial','ambiguous','unconfirmed','uncertain_action']){
  const data={events:[e],inbox:[{id:e.id,source:'human'}],turn:{actions:[],speech_operations:[{id:'speech',status:'submitted',reply_to:[publicSource(e)],packets:[{text:'First',status:'submitted'},{text:'Second',status:'submitted'}]}]}};
  const op=data.turn.speech_operations[0],transport={kind:'server_player_uuid',username:'Self',uuid:'00000000-0000-0000-0000-000000000001'};
  if(variant==='ambiguous')op.packets[1].text='First';
  assert.equal(confirmEcho(data,'First',transport,'Self',e.time),variant!=='ambiguous');
  if(variant==='uncertain_action'){confirmEcho(data,'Second',transport,'Self',e.time);data.turn.actions.push({status:'uncertain'});}
  if(variant==='partial')op.status='incomplete';
  settleReplies(data);
  assert.equal(data.inbox.length,1,variant);
 }
});
