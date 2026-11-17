// Internal, action-local evidence for a completed operation that missed its goal.
// Never trust error text, JSON fields, caller arguments or timeouts as proof.
// Passing the marker into sub-operations preserves composition without allowing
// an error object from an earlier action to settle a later one.
function create(){
 const evidence=new WeakMap();
 return {
  settled(error,details){
   if(!error||typeof error!=='object'||!details||typeof details.kind!=='string')throw Error('Invalid internal settlement evidence');
   evidence.set(error,structuredClone({...details,replayed:false}));return error;
  },
  get(error){const value=error&&typeof error==='object'?evidence.get(error):null;return value?structuredClone(value):null;}
 };
}
module.exports={create};
