/* Browser-free regression: exercise the exact predicate in voice-browser.cjs. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'voice-browser.cjs'), 'utf8');
const line = source.split('\n').find(x => x.startsWith('const taskCalls = '));
assert(line, 'voice harness task predicate must be present');
const taskCalls = vm.runInNewContext(`${line}\ntaskCalls;`);
const metadata = ['/api/config', '/api/overview-provider', '/api/config?v=1', '/api/overview-provider?v=1', '/wizard-search/api/overview-provider'];
assert.equal(taskCalls(metadata).length, 0);
const operations = ['/api/web?q=x', '/api/web?q=x', '/api/overview-stream?q=x', '/api/overview-stream?q=x', '/api/overview', '/api/chat', '/api/translate', '/api/read-image', '/api/config-extra', '/api/overview-provider-extra'];
assert.equal(JSON.stringify(taskCalls([...metadata, ...operations])), JSON.stringify(operations));
const baseline = taskCalls(['/api/config', '/api/web?q=x']);
for (const injected of ['/api/web?q=x', '/api/overview-stream?q=x']) {
  assert.notEqual(JSON.stringify(taskCalls(['/api/config', '/api/web?q=x', '/api/overview-provider', injected])), JSON.stringify(baseline), `must detect injected ${injected}`);
}
console.log('PASS: metadata excluded; exact search/inference sequences and injected duplicates retained');
