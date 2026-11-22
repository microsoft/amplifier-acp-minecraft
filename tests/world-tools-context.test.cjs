const test = require('node:test');
const assert = require('node:assert/strict');
const {query} = require('../world-tools-context.cjs');
const cfg = {username: 'Builder', conversation_id: 'world-a', context_grant: 'one-world'};
const grant = {mode: 'grant', grant: 'one-world'};
const event = {kind: 'chat', username: 'Sam', message: 'Welcome', id: 'hello', provenance: 'minecraft_public_chat'};
const history = {
  legacy: {events: [{...event, id: 'previous'}], task: {goal: 'private assignment'}},
  data: {events: [event, {...event, whisper: true, message: 'private whisper'},
    {kind: 'action_result', result: 'private operation'},
    {...event, provenance: 'operator_control', message: 'private operator input'}]}
};

test('a world grant discovers its own conversation and reads only public history', () => {
  const request = operation => query({operation, access: grant}, cfg, history, {connected: true});
  const [current] = request('list').items;
  assert.deepEqual(current.read, {operation: 'read', conversation_id: 'world-a'});
  assert.equal(current.activity.connected, true);
  const result = request('read');
  assert.deepEqual(result.messages.map(m => m.id), ['previous', 'hello']);
  assert.doesNotMatch(JSON.stringify(result), /private/);
  assert.equal(request('authorize').actor_id, 'minecraft:Builder');
  assert.throws(() => query({operation: 'read', conversation_id: 'world-b', access: grant}, cfg, history, {}));
  assert.throws(() => query({operation: 'list', access: {mode: 'grant', grant: 'wrong'}}, cfg, history, {}));
});
