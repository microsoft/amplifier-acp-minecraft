const {EventEmitter}=require('node:events');
function inventoryClient(write){
 const c=new EventEmitter();
 c.write=(name,p)=>name==='ping_request'?c.emit('ping_response',p):write(name,p);
 return c;
}
module.exports={inventoryClient};
