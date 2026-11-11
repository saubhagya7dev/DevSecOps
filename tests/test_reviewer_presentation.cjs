const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');
const start = source.indexOf('function renderRecommendations(a) {');
const end = source.indexOf('function renderEvidence(a)', start);
const context = vm.createContext({
  esc: value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  empty: (title, detail) => `<p>${title}</p><p>${detail}</p>`,
  evidenceLinks: ids => ids.join(' '), icon: () => '',
});
vm.runInContext(source.slice(start, end), context);
function render(findings, questions = []) {
  return context.renderRecommendations({research:{status:'failed',incidents:[],research_limitations:[]},
    review:{summary:'Repository review completed.',scope:'repository-only',findings,
      existing_defenses:[],rejected_matches:[],questions}});
}
test('failed incident research does not hide accepted repository improvements', () => {
  const html = render([{classification:'Repository improvement',id:'R1',title:'Review inputs',impact:'Low',confidence:'Low',
    reasoning:'Code scoped check',prerequisite:'Confirm input origin',counterevidence:'Controls may exist',action:'Inspect validation',
    verification:'Read tests',missing_information:[],evidence_ids:['E1'],incident_ids:[]}]);
  assert.match(html, /Repository improvement/);
  assert.match(html, /Inspect validation/);
  assert.match(html, /Verification scope/);
  assert.doesNotMatch(html, /Security review was not performed|data-incident=/);
});
test('questions remain visible when no direct repository evidence supports findings', () => {
  const html = render([], ['Provide inspectable input-boundary code.']);
  assert.match(html, /Questions for the builder/);
  assert.match(html, /Provide inspectable input-boundary code/);
  assert.doesNotMatch(html, /Security review was not performed/);
});
test('untrusted reviewer text is escaped in improvement cards and builder questions', () => {
  const html = render([], ['<script>steal()</script>']);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});
