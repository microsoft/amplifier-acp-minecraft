const {packets}=require('./speech.cjs');
const installationInputs=require('./installation-inputs.cjs');

function readPrivate(history,id) {
  if(typeof id!=='string'||!id)throw Error('A private input id is required');
  const event=history.data.events.find(e=>e.id===id && (e.whisper || e.provenance==='operator_control'));
  if(!event)throw Error('No current private input with this id');
  return event;
}

function reply(history,bot,args) {
  const source=readPrivate(history,args.request_id);
  if(typeof args.text!=='string'||!args.text.trim()||Buffer.byteLength(args.text)>4000)throw Error('Unsupported reply text');
  const prior=history.receipt(args.operation_id);
  if(prior) {
    history.begin('private_reply',args);
    if(prior.status!=='completed')throw Error('Private reply has an unsettled receipt');
    return prior.result;
  }
  let send;
  if(source.whisper) {
    const target=bot.players[source.username];
    if(!/^\w{1,16}$/.test(source.username)||source.transport?.kind!=='server_player_uuid'||
       !source.transport.uuid || target?.uuid?.toLowerCase()!==source.transport.uuid.toLowerCase())throw Error('Original whisper player identity is unavailable');
    const parts=packets(args.text);
    send=()=>{for(const part of parts)bot.whisper(source.username,part);return {transport_submitted:true,request_id:source.id};};
  } else if(source.installation_source) {
    const route=installationInputs.replyRoute(history.data,[source.id]);
    const record=installationInputs.replyRecord(history.data,route);
    if((record.source_replies||[]).length>=installationInputs.capability.source_replies.max_items)throw Error('Caller reply capacity reached');
    send=()=>{
      record.source_replies=[...(record.source_replies||[]),{id:args.operation_id,text:args.text,at:new Date().toISOString(),
        audience:structuredClone(record.source.audience),delivery:'recorded'}];
      return {recorded:true,request_id:source.id};
    };
  } else {
    send=()=>{history.record('operator_reply',{request_id:source.id,text:args.text});return {recorded:true,request_id:source.id};};
  }
  const {entry}=history.begin('private_reply',args);
  try {
    const result=send();
    history.data.inbox=history.data.inbox.filter(e=>e.id!==source.id);
    return history.finish(entry,'completed',result);
  }catch(error){history.finish(entry,'unknown',{error:error.message});throw error;}
}
module.exports={readPrivate,reply};
