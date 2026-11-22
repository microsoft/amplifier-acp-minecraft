const test=require('node:test'),assert=require('node:assert/strict');
const {packets}=require('../speech.cjs');
test('completed speech preserves every word and address within UTF-16 wire length',()=>{
 const text=('Look at this landing 😀. '+'Another useful observation with detail. ').repeat(25),prefix='@Builder [FYI] ';
 const chunks=packets(text,prefix);
 assert.ok(chunks.length>1);assert.ok(chunks.every(c=>c.length<=240&&c.startsWith(prefix)&&!/[\uD800-\uDBFF]$/.test(c)));
 assert.equal(chunks.map(c=>c.slice(prefix.length)).join(' '),text.trim());
});
test('commands, empty and oversized utterances reject before any transport',()=>{
 for(const t of ['/kill','', 'x'.repeat(4001)])assert.throws(()=>packets(t));
});
