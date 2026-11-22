// Existing enrolled source providers run this fixed filename before cutover.
// Exercise their actual idle observation fields against the current body.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {fixture} = require('./world-body-fixture.cjs');

test('an installed update participant can verify the original world while its gate is closed', async t => {
  const task = {id:'original', status:'waiting', deadline:1, turns:4};
  const f = await fixture(t, {}, {task, unknown_receipts:['unsettled']});
  const gate = {version:1, transaction_id:'owned-update', closed:true};
  const directory = path.join(f.home, 'installation-updates');
  fs.mkdirSync(directory);
  fs.writeFileSync(path.join(directory, 'gate.json'), JSON.stringify(gate));

  const effect = await f.call('chat', {text:'must stay held', operation_id:'gate-refusal-001'});
  assert.ok(effect.isError);
  assert.deepEqual(f.sends, []);
  for (const route of ['/installation-state', '/status']) {
    const {status,value} = await f.request(route);
    assert.equal(status, 200);
    assert.equal(value.version, 1);
    assert.equal(value.ready, true);
    assert.equal(value.busy, false);
    assert.equal(value.turn_active, false);
    assert.equal(value.action_sequence, null);
    assert.deepEqual(value.action_lease, {version:1,lease_id:null,expires_at:0,renewable:false});
    assert.deepEqual(value.task, task);
    assert.deepEqual(value.inventory, {slots:[],cursor:null});
    assert.deepEqual(value.position, {x:0,y:64,z:0});
    assert.equal(value.window_open, false);
    assert.deepEqual(value.admission_gate, gate);
  }
});
