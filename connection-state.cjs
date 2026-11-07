// Offline intent survives service restarts. Only the owner Connect operation
// opens transport; it keeps world admission closed until session verification.
const fs=require('node:fs'),path=require('node:path');
function transportAllowed(home){
 let v;try{v=JSON.parse(fs.readFileSync(path.join(home,'installation-connections/state.json'),'utf8'));}
 catch(e){if(e.code==='ENOENT')return true;throw e;}
 if(v.schema!==1||!['disconnecting','disconnected','connecting','connected'].includes(v.phase)||typeof v.request_id!=='string')throw Error('Invalid saved connection intent');
 return ['connecting','connected'].includes(v.phase);
}
module.exports={transportAllowed};
