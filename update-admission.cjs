// Installation-owned gate, separate from task/Stop authority. Never expires on a
// timer: only its transaction owner may release it after verified restoration.
const fs=require('node:fs'),path=require('node:path');
const file=home=>path.join(home,'installation-updates','gate.json');
function state(home){
 try{const v=JSON.parse(fs.readFileSync(file(home),'utf8'));
  if(v.version!==1||typeof v.transaction_id!=='string'||!v.transaction_id||v.closed!==true)throw Error('Malformed installation admission gate');
  return v;
 }catch(e){if(e.code==='ENOENT')return null;throw e;}
}
function requireOpen(home){if(state(home))throw Error('Installation update has closed new admission; input is retained');}
module.exports={state,requireOpen};
