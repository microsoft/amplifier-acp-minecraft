const test=require('node:test'),assert=require('node:assert/strict');
const {protocolCompatibility,translationMetadata}=require('../protocol-compatibility.cjs');
test('only the unused legacy recipe-book payload is opaque; inventory still decodes',()=>{
 const {createDeserializer,createSerializer}=require('minecraft-protocol/src/transforms/serializer');
 const opts={state:'play',version:'1.21.1',customPackets:protocolCompatibility('1.21.1')};
 const reader=createDeserializer(opts);
 const payload=Buffer.from([0x77,0xff,0xff,0xff,0x7f,0]);
 const r=reader.parsePacketBuffer(payload);assert.equal(r.data.name,'declare_recipes');assert.deepEqual(r.data.params,payload.subarray(1));
 const encoded=createSerializer({...opts,isServer:true}).createPacketBuffer({name:'window_items',params:{windowId:0,stateId:3,items:[],carriedItem:{itemCount:0}}});
 const inv=reader.parsePacketBuffer(encoded);assert.equal(inv.data.name,'window_items');assert.equal(inv.data.params.stateId,3);
 assert.throws(()=>reader.parsePacketBuffer(encoded.subarray(0,encoded.length-1)));
 assert.equal(protocolCompatibility('26.1'),undefined);
});
test('only exact empty ViaBackwards bookkeeping counts as ordinary supply metadata',()=>{
 const c={type:'custom_data',data:{type:'compound',value:{'VV|custom_data':{type:'byte',value:1},'VV|original_hashes':{type:'compound',value:{id:{type:'int',value:134},backup_tag:{type:'string',value:'VB|Protocol1_21_5To1_21_4'},removed:{type:'intArray',value:[]}}}}}};
 assert.equal(translationMetadata(c),true);
 for(const mutate of [x=>x.type='custom_name',x=>x.data.value.secret={type:'string',value:'custom'},x=>x.data.value['VV|original_hashes'].value.removed.value.push(5),x=>x.data.value['VV|original_hashes'].value.damage={type:'int',value:1}]){
  const bad=structuredClone(c);mutate(bad);assert.equal(translationMetadata(bad),false);
 }
});
