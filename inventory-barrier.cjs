// Inventory snapshots may arrive more than once for one click through a version
// proxy. A matching server pong drains those preceding responses before another
// click or a verification reads the inventory. It does not predict any slots.
let sequence=0;
function idOf(v){return Array.isArray(v)?((BigInt(v[0]>>>0)<<32n)|BigInt(v[1]>>>0)).toString():String(v);}
function inventoryBarrier(bot,{timeout=5000}={}){
 const id=++sequence;
 return new Promise((resolve,reject)=>{
  const client=bot._client;
  const clean=()=>{clearTimeout(timer);client.off('ping_response',pong);client.off('end',ended);};
  const pong=p=>{if(idOf(p.id)===String(id)){clean();resolve();}};
  const ended=()=>{clean();reject(Error('Connection ended before inventory synchronization'));};
  const timer=setTimeout(()=>{clean();reject(Error('Server did not confirm inventory synchronization'));},timeout);
  client.on('ping_response',pong);client.once('end',ended);
  try{client.write('ping_request',{id:BigInt(id)});}catch(e){clean();reject(e);}
 });
}
module.exports={inventoryBarrier};
