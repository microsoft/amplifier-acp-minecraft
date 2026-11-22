// One process owns this installation's player. Historical workshop data is read-only.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

function read(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch (error) { if (error.code === 'ENOENT') return fallback; throw error; }
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
}

// Bind the observable target, rather than treating the whole game as one
// effect. Compound tools also bind the player movement they can initiate.
function effectKeys(tool,args={}) {
  if(['chat','tell'].includes(tool)) {
    if(typeof args.text!=='string')return ['public:*'];
    const prefix=tool==='tell'?'@'+args.player+' ':'';
    const packets=require('./speech.cjs').packets(args.text,prefix);
    return packets.map(text=>'public:'+crypto.createHash('sha256').update(text).digest('hex'));
  }
  if(tool==='private_reply')return [args.request_id?'private:'+args.request_id:'private:*'];
  if(['move','follow'].includes(tool))return ['world:movement'];
  if(['attack','shear'].includes(tool))return [args.uuid?'world:entity:'+args.uuid.toLowerCase():'world:*'];
  if(tool==='equip')return ['world:main_hand'];
  if(tool==='consume')return ['world:consume'];
  if(tool==='give')return [args.player?'world:give:'+args.player.toLowerCase():'world:*'];
  if(tool==='craft')return ['world:craft','world:movement'];
  const coords=tool==='gather'?args.targets:tool==='build'?args.blocks:[args];
  if(!['gather','build','dig','place','container','furnace','set_open','activate_control','write_sign','till'].includes(tool) ||
     !Array.isArray(coords)||!coords.length||coords.some(p=>!p||![p.x,p.y,p.z].every(Number.isInteger)))return ['world:*'];
  const keys=new Set();
  const block=(x,y,z)=>keys.add('world:block:'+x+','+y+','+z);
  for(const {x,y,z} of coords) {
    block(x,y,z);
    // Either half of a bed, door or double chest can name the same object.
    if(args.item?.endsWith('_door')||args.expected?.endsWith('_door')){block(x,y+1,z);block(x,y-1,z);}
    if([args.item,args.expected,args.block].some(id=>id==='chest'||id?.endsWith('_bed'))){
      block(x-1,y,z);block(x+1,y,z);block(x,y,z-1);block(x,y,z+1);
    }
  }
  if(['place','build','gather'].includes(tool))keys.add('world:movement');
  return [...keys];
}
function overlaps(first,second) {
  return first.some(left=>second.some(right=>left===right ||
    left.endsWith(':*')&&right.startsWith(left.slice(0,-1)) ||
    right.endsWith(':*')&&left.startsWith(right.slice(0,-1))));
}

function previouslyReviewed(turn,action) {
  const review=action.review;
  if(!review || action.status!=='uncertain')return false;
  const original={...turn,actions:turn.actions.map(a=>{
    if(!a.review || a.review.original_turn_sha256!==review.original_turn_sha256)return a;
    const {review:omitted,...prior}=a;
    return prior;
  })};
  delete original.effect_review;
  const digest=crypto.createHash('sha256').update(JSON.stringify(original)).digest('hex');
  if(review.original_turn_sha256!==digest)return false;
  if(review.outcome==='no_effect')return true;
  return turn.effect_review?.future_work_only===true &&
         turn.effect_review.original_turn_sha256===digest &&
         turn.effect_review.result?.action_ids?.includes(action.id);
}

function fingerprint(args) {
  const { operation_id, ...fields } = args;
  return crypto.createHash('sha256').update(JSON.stringify(canonical(fields))).digest('hex');
}

class WorldToolsState {
  constructor(home) {
    this.directory = path.join(home, 'world-tools');
    this.file = path.join(this.directory, 'state.json');
    this.legacy = read(path.join(home, 'workshop.json'), {});
    this.data = read(this.file, {
      version: 1, events: [], public_inbox: [], operations: {}, inbox: [],
      stopped: this.legacy.activity_stop || (this.legacy.task?.status === 'stopped' ? {source:'legacy_stop'} : null),
      block_controls: this.legacy.block_controls || {},
      installation_input_receipts: this.legacy.installation_input_receipts || {},
      task_source_cutoff: this.legacy.task_source_cutoff || 0
    });
    if (this.data.version !== 1 || !Array.isArray(this.data.public_inbox) || !Array.isArray(this.data.inbox) ||
        !Array.isArray(this.data.events) || !this.data.operations || Array.isArray(this.data.operations) ||
        typeof this.data.operations !== 'object' || !Object.hasOwn(this.data,'stopped')) throw Error('Invalid world tools state');
    for(const [id,entry] of Object.entries(this.data.operations)) {
      if(!entry || entry.id!==id || typeof entry.tool!=='string' || !/^[a-f0-9]{64}$/.test(entry.arguments_hash) ||
         (entry.effect_keys!==undefined && (!Array.isArray(entry.effect_keys)||!entry.effect_keys.length||entry.effect_keys.some(k=>typeof k!=='string'||!k))) ||
         !['started','unknown','completed','failed_settled'].includes(entry.status))throw Error('Invalid operation receipt');
    }
    this.healthy = true;
  }

  save() {
    if (!this.healthy) throw Error('Receipt storage failed; operator reconciliation required');
    // An I/O error can occur after rename. Never dispatch again in this process.
    try {
      const created=fs.mkdirSync(this.directory, {mode:0o700, recursive:true});
      if(created && process.platform!=='win32') {
        const home=fs.openSync(path.dirname(this.directory),'r');
        try { fs.fsyncSync(home); } finally { fs.closeSync(home); }
      }
      const temp = this.file + '.' + crypto.randomUUID();
      const fd = fs.openSync(temp, 'wx', 0o600);
      try { fs.writeFileSync(fd, JSON.stringify(this.data)); fs.fsyncSync(fd); }
      finally { fs.closeSync(fd); }
      fs.renameSync(temp, this.file);
      if (process.platform !== 'win32') {
        const directory = fs.openSync(this.directory, 'r');
        try { fs.fsyncSync(directory); } finally { fs.closeSync(directory); }
      }
    } catch (error) { this.healthy = false; throw error; }
  }

  task() { return null; }

  record(kind, fields, enqueue=false) {
    const event = {...fields, kind, id:crypto.randomUUID(), time:new Date().toISOString()};
    this.data.events.push(event);
    // An unanswered caller retains its bound event even when the rolling public
    // observation window advances. It can only be retrieved on the private API.
    const pendingIds=new Set(this.data.inbox.map(m=>m.id));
    const recent=this.data.events.slice(-2000);
    this.data.events=[...this.data.events.slice(0,-2000).filter(e=>pendingIds.has(e.id)),...recent];
    if (enqueue) this.data.public_inbox.push(event);
    this.save();
    return event;
  }

  acknowledge(id) {
    if (typeof id !== 'string' || this.data.public_inbox[0]?.id !== id) throw Error('Input is no longer the pending head');
    this.data.public_inbox.shift();
    this.save();
    return {acknowledged:true,id};
  }

  receipt(id) {
    return Object.hasOwn(this.data.operations, id) ? this.data.operations[id] : null;
  }

  begin(tool, args) {
    const id = args.operation_id;
    if (typeof id !== 'string' || !/^[a-zA-Z0-9_-]{8,100}$/.test(id) || Object.hasOwn(Object.prototype,id))
      throw Error('A stable operation_id is required for a Minecraft effect');
    const digest = fingerprint(args);
    const prior = this.receipt(id);
    if (prior) {
      if (prior.tool !== tool || prior.arguments_hash !== digest) throw Error('Operation ID already binds different arguments');
      return {prior};
    }
    const keys=effectKeys(tool,args);
    for (const old of Object.values(this.data.operations)) {
      if (['started','unknown'].includes(old.status) && overlaps(keys,old.effect_keys||effectKeys(old.tool)))
        throw Error('An overlapping action has an uncertain receipt. Inspect operation ' + old.id);
    }
    // Old journals may contain only an action id. An unattributed interrupted
    // effect cannot be narrowed to a particular world tool.
    if ((this.legacy.action_sequences||[]).some(seq=>['running','interrupted'].includes(seq.status)) && overlaps(keys,['world:*']))
      throw Error('Historical sequence has unconfirmed effects');
    for (const turn of [this.legacy.turn,this.legacy.last_turn,this.legacy.last_conversation_turn]) {
      if (!turn) continue;
      for (const action of turn.actions || []) {
        if(id===action.id)throw Error('Operation id belongs to historical work');
        if(['succeeded','failed_settled'].includes(action.status) || previouslyReviewed(turn,action))continue;
        const evidence = (this.legacy.events || []).find(e => e.kind === 'action_started' && e.action_id === action.id);
        if (!evidence || overlaps(keys,effectKeys(evidence.action,evidence.arguments))) throw Error('Historical action requires reconciliation: ' + action.id);
      }
    }
    const entry = {id,tool,arguments_hash:digest,effect_keys:keys,status:'started',at:new Date().toISOString()};
    this.data.operations[id] = entry;
    this.save(); // Persist intent before the first possible game packet.
    return {entry};
  }

  finish(entry, status, result) {
    Object.assign(entry, {status,result,finished_at:new Date().toISOString()});
    this.save();
    return result;
  }
}
module.exports = {WorldToolsState};
