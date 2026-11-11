const test = require('node:test');
const assert = require('node:assert/strict');
const {createLoader, shouldApply} = require('../web/job-updates.js');

test('status-only revisions retain existing evidence without a payload request', async () => {
  const paths = [];
  const load = createLoader(async path => {
    paths.push(path);
    return {id: 'a', revision: 4, payload_revision: 2, status: 'running'};
  });
  const previous = {id: 'a', revision: 3, payload_revision: 2, artifacts: {saved: true}, report: ''};
  const next = await load('a', previous);
  assert.deepEqual(paths, ['/api/jobs/a/status']);
  assert.equal(next.artifacts, previous.artifacts);
  assert.equal(next.revision, 4);
});

test('new evidence fetches a consistent full snapshot and coalesces concurrent refreshes', async () => {
  const paths = [];
  const complete = {id: 'a', revision: 6, payload_revision: 3, artifacts: {new: true}};
  const load = createLoader(async path => {
    paths.push(path);
    await Promise.resolve();
    return path.endsWith('/status') ? {id: 'a', revision: 5, payload_revision: 3} : complete;
  });
  const previous = {id: 'a', revision: 4, payload_revision: 2};
  const first = load('a', previous);
  assert.equal(first, load('a', previous));
  assert.equal(await first, complete);
  assert.deepEqual(paths, ['/api/jobs/a/status', '/api/jobs/a']);
});

test('a failed refresh releases its slot so the next attempt can recover', async () => {
  let fail = true;
  const load = createLoader(async () => {
    if (fail) throw new Error('offline');
    return {id: 'a', revision: 1, payload_revision: 0};
  });
  await assert.rejects(load('a'), /offline/);
  fail = false;
  assert.equal((await load('a')).revision, 1);
});

test('late, duplicate, and previously selected job responses cannot regress the UI', () => {
  const current = {id: 'a', revision: 9};
  assert.equal(shouldApply('a', current, {id: 'a', revision: 8}), false);
  assert.equal(shouldApply('a', current, {id: 'a', revision: 9}), false);
  assert.equal(shouldApply('b', null, {id: 'a', revision: 10}), false);
  assert.equal(shouldApply('a', current, {id: 'a', revision: 10}), true);
  assert.equal(shouldApply('a', null, {id: 'a', revision: 1}), true);
});
