// Fixed installation-owned HTTP routes, not arbitrary model HTTP access.
// Capability/actor/receipt validation belongs above this transport boundary.
class HuddleHttp {
 #token;
 constructor({url,room_id,token},{fetch=globalThis.fetch,timeoutMs=15000,maxBytes=1048576}={}){
  const host=new URL(url);
  if(host.username||host.password||host.search||host.hash||host.pathname!=='/'||!(host.protocol==='https:'||host.protocol==='http:'&&['127.0.0.1','[::1]'].includes(host.hostname)))throw Error('Use an enrolled HTTPS or numeric loopback huddle host');
  if(typeof room_id!=='string'||!room_id||room_id.length>160||typeof token!=='string'||token.length<32||/[\r\n]/.test(token))throw Error('Fixed room and private participant credential required');
  this.host=host.origin;this.room=room_id;this.#token=token;this.fetch=fetch;this.timeoutMs=timeoutMs;this.maxBytes=maxBytes;
 }
 async request(suffix,{method='GET',body,notFound=false}={}){
  return this.requestPath(`/api/v1/huddles/${encodeURIComponent(this.room)}${suffix}`,{method,body,notFound});
 }
 async requestPath(path,{method='GET',body,notFound=false}={}){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),this.timeoutMs);
  try{
   const response=await this.fetch(`${this.host}${path}`,{method,redirect:'error',signal:controller.signal,
    headers:{Authorization:`Bearer ${this.#token}`,Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
   if(notFound&&response.status===404){await response.body?.cancel();return {found:false};}
   if(!response.ok){await response.body?.cancel();throw Error(`Huddle HTTP ${response.status}`);}
   if(!response.headers.get('content-type')?.toLowerCase().includes('application/json')){await response.body?.cancel();throw Error('Huddle returned non-JSON evidence');}
   if(Number(response.headers.get('content-length'))>this.maxBytes){await response.body?.cancel();throw Error('Huddle response exceeds bounded read');}
   const chunks=[];let count=0;
   for await(const chunk of response.body){count+=chunk.length;if(count>this.maxBytes){controller.abort();throw Error('Huddle response exceeds bounded read');}chunks.push(chunk);}
   const value=JSON.parse(Buffer.concat(chunks).toString('utf8'));return notFound?{found:true,value}:value;
  }catch(error){
   // Do not echo response bodies, URLs, tokens or implementation diagnostics.
   if(/^Huddle (HTTP \d{3}|returned non-JSON evidence|response exceeds bounded read)$/.test(error.message))throw error;
   throw Error('Huddle request outcome unavailable; query the original operation before any further send');
  }finally{clearTimeout(timer);}
 }
 descriptor(){return this.request('');}
 messages(after=0,limit=20){
  if(!Number.isSafeInteger(after)||after<0||!Number.isInteger(limit)||limit<1||limit>100)throw Error('Use a valid huddle cursor and bounded page');
  return this.request(`/messages?after=${after}&limit=${limit}`);
 }
 post(payload){return this.request('/posts',{method:'POST',body:payload});}
 status(id){
  if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id))throw Error('Original huddle operation UUID required');
  return this.request(`/posts/${id}`,{notFound:true});
 }
}
class HuddleInstallationHttp extends HuddleHttp {
 constructor(config,options){super({...config,room_id:'installation'},options);}
 roster(){return this.requestPath('/api/v1/huddles/roster');}
 ensure(payload){return this.requestPath('/api/v1/huddles/ensure',{method:'POST',body:payload});}
 ensureStatus(id){
  if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id))throw Error('Original huddle operation UUID required');
  return this.requestPath(`/api/v1/huddles/ensure/${id}`,{notFound:true});
 }
 discovery(after=0,limit=16){
  if(!Number.isSafeInteger(after)||after<0||!Number.isInteger(limit)||limit<1||limit>50)throw Error('Use a valid discovery cursor and bounded page');
  return this.requestPath(`/api/v1/huddles/discovery?after=${after}&limit=${limit}`);
 }
}
module.exports={HuddleHttp,HuddleInstallationHttp};
