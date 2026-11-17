// Internal evidence for a completed operation that did not achieve its goal.
// Never trust an error message, JSON field, caller argument or timeout as proof.
// Weak identity keeps evidence local to the exact error; composed tools retain it.
const evidence=new WeakMap();
function settled(error,details){
 if(!error||typeof error!=='object'||!details||typeof details.kind!=='string')throw Error('Invalid internal settlement evidence');
 evidence.set(error,structuredClone({...details,replayed:false}));return error;
}
function get(error){const value=error&&typeof error==='object'?evidence.get(error):null;return value?structuredClone(value):null;}
module.exports={settled,get};
