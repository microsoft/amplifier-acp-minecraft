// The agent owns timing. This installation only admits and claims an immediate
// request on its already-bound game session. Never redispatch a claimed wake.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

function binding(home) {
  const {session, binding} = JSON.parse(fs.readFileSync(path.join(home,'session.json'),'utf8'));
  if (!session || !binding || typeof session !== 'string' || typeof binding !== 'string') throw Error('No saved game session');
  return {session, binding};
}
function queue(history, home, {id,note}, admit) {
  if (!history.healthy) throw Error('Wake storage outcome unknown');
  const saved = binding(home);
  const key = crypto.createHash('sha256').update(id).digest('hex');
  const digest = crypto.createHash('sha256').update(JSON.stringify([saved.session,saved.binding,note])).digest('hex');
  const wakes = history.data.agent_wakes ??= {receipts:{}, current:null};
  const prior = wakes.receipts[key];
  if (prior) {
    if (prior.digest !== digest) throw Error('Wake ID already bound to other input or session');
    if (prior.state === 'cancelled') {
      const error = Error('Wake cancelled before dispatch');
      error.details = {queued:false,id};
      throw error;
    }
    return {queued:true,id};
  }
  admit();
  if (wakes.current) throw Error('A wake is already queued or awaiting its outcome');
  wakes.receipts[key] = {state:'queued',digest};
  wakes.current = {key,id,note,...saved,time:new Date().toISOString()};
  history.save();
  return {queued:true,id};
}
function pending(history) {
  const wakes=history.data.agent_wakes, current=wakes?.current;
  if (!current || wakes.receipts[current.key].state !== 'queued') return null;
  const {id,note,session,binding,time}=current;
  return {id,note,session,binding,time,source:'agent_wake'};
}
function transition(history, args, from, to) {
  const wakes=history.data.agent_wakes, current=wakes?.current;
  if (!current || current.id!==args.id || current.session!==args.session || current.binding!==args.binding ||
      wakes.receipts[current.key].state!==from) throw Error('Wake no longer matches the pending request');
  wakes.receipts[current.key].state=to;
  if (to!=='claimed') wakes.current=null;
  history.save();
  return {id:args.id,state:to};
}
module.exports={binding,queue,pending,transition};
