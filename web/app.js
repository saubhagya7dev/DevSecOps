'use strict';

const paths = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  history: '<path d="M3 11a9 9 0 1 1 2.5 7M3 4v7h7M12 7v5l3 2"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 16l10 5 10-5"/>',
  'arrow-up-right': '<path d="M6 18 18 6M6 6h12v12"/>',
  'arrow-right': '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  shield: '<path d="m12 2 8 4v6c0 5-5 8-8 10-3-2-8-5-8-10V6Z"/>',
  'shield-check': '<path d="m12 2 8 4v6c0 5-5 8-8 10-3-2-8-5-8-10V6Z"/><path d="m8 12 3 3 5-6"/>',
  settings: '<path d="m9 3-1 3-3 1-2 4 2 2v3l3 2 1 3h5l1-3 3-2v-3l2-2-2-4-3-1-1-3Z"/><circle cx="11.5" cy="12" r="3"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  code: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-14-2 16"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  github: '<path d="M9 19c-4 1-4-2-6-2m12 5v-4a3.5 3.5 0 0 0-1-3c3-.3 6-1.5 6-6a5 5 0 0 0-1.5-3.5 4.5 4.5 0 0 0-.1-3.5S17 1.5 14.5 3a13 13 0 0 0-7 0C5 1.5 3.6 2 3.6 2a4.5 4.5 0 0 0-.1 3.5A5 5 0 0 0 2 9c0 4.5 3 5.7 6 6a3.5 3.5 0 0 0-1 3v4"/>',
  globe: '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
  pulse: '<path d="M2 12h5l3-8 4 16 3-8h5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
  x: '<path d="m6 6 12 12M6 18 18 6"/>',
  file: '<path d="M14 2H5v20h14V7Zm0 0v6h5M8 12h8m-8 4h8"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>'
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.file}</svg>`;
document.querySelectorAll('[data-icon]').forEach(el => { el.innerHTML = icon(el.dataset.icon); });
const $ = id => document.getElementById(id);
const scrollToElement = (el, block = 'start') => el?.scrollIntoView({
  behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block
});
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const safeUrl = value => { try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password ? u.href : '#'; } catch { return '#'; } };
const link = (url, text, cls = '') => `<a class="${esc(cls)}" href="${esc(safeUrl(url))}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>`;
const terminal = new Set(['completed', 'partial', 'failed', 'cancelled']);
const stageNames = {prepare:'Preparation', analyst:'Repository Analyst', researcher:'Incident Researcher', reviewer:'Security Reviewer', validation:'Report validation'};
let config, current, currentId, activeTab = 'overview', eventStream, reloadTimer, eventItems = [], recent = [], isSubmitting = false;

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: {'Content-Type':'application/json', ...(options.method ? {'X-Review-Token':config?.token || ''} : {}), ...options.headers} });
  let data;
  try { data = await response.json(); } catch { throw new Error('The local server returned an unreadable response.'); }
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}

function empty(title, detail, symbol = 'layers') {
  return `<div class="empty-state"><div class="empty-visual">${icon(symbol)}</div><h3>${esc(title)}</h3><p>${esc(detail)}</p></div>`;
}

function showToast(text) {
  document.querySelector('.toast')?.remove();
  const el = document.createElement('div'); el.className = 'toast'; el.setAttribute('role','status'); el.textContent = text;
  document.body.append(el); setTimeout(() => el.remove(), 3500);
}

function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll('.tab').forEach(el => { const selected = el.dataset.tab === tab; el.classList.toggle('active', selected); el.setAttribute('aria-selected', String(selected)); el.tabIndex = selected ? 0 : -1; });
  $('result-content').setAttribute('aria-labelledby', `tab-${tab}`);
  renderResults();
}

function evidenceLinks(ids) {
  return ids.map(id => `<a href="#" data-evidence="${esc(id)}">${esc(id)} ${icon('arrow-up-right')}</a>`).join('');
}

function renderOverview(a) {
  if (!a.profile) {
    const title = current && !terminal.has(current.status) ? 'The investigation is underway' : current ? 'Repository profile unavailable' : 'A repository. A few agents. A clearer picture.';
    const detail = current ? 'The evidence panel fills as each stage completes. Any saved artifacts remain available even if a later stage fails.' : 'Paste a public GitHub link above. We’ll inspect the code, research relevant attacks, and connect the evidence for you.';
    return empty(title, detail, 'code') + (!current ? '<div class="empty-tags"><span>Commit-pinned evidence</span><span>Primary sources</span><span>Explicit uncertainty</span></div>' : '');
  }
  const p = a.profile, coverage = a.repository?.coverage || {};
  return `<p class="summary">${esc(p.summary)}</p>
    <h3 class="subheading">Technology observed</h3><div class="tech-grid">${p.technologies.map(t => `<div class="tech-tag">${esc(t.name)}<small>${esc(t.version)}</small></div>`).join('') || '<span class="muted">No technology claims passed citation checks.</span>'}</div>
    <h3 class="subheading">Application components</h3>${p.components.map(c => `<div class="component"><strong>${esc(c.name)}</strong><p>${esc(c.description)}</p><div class="citation-links">${evidenceLinks(c.evidence_ids)}</div></div>`).join('') || '<p class="note">No components established within the inspected evidence.</p>'}
    <h3 class="subheading">Analysis coverage</h3><div class="coverage-grid"><div class="metric"><strong>${esc(coverage.files_read ?? 0)}</strong><span>files inspected</span></div><div class="metric"><strong>${esc(coverage.files_in_tree ?? 0)}</strong><span>files in returned tree</span></div><div class="metric"><strong>${p.observations.length}</strong><span>cited observations</span></div></div>
    <p class="note">A bounded selection of files was inspected. ${esc(coverage.truncated_files || 0)} file(s) were truncated. ${coverage.tree_truncated ? 'GitHub returned an incomplete tree. ' : ''}Production exposure is unknown.</p>
    <h3 class="subheading">Questions guiding the research</h3><ul class="unknown-list">${p.research_questions.map(q => `<li>${esc(q)}</li>`).join('')}</ul>
    <h3 class="subheading">What we cannot establish</h3><ul class="unknown-list">${p.unknowns.map(q => `<li>${esc(q)}</li>`).join('')}</ul>`;
}

function renderIncidents(a) {
  if (!a.research) return empty('Research has not arrived yet', 'Documented attacks and retrieved passages will appear after the Incident Researcher completes its work.', 'search');
  const r = a.research, sources = Object.fromEntries(r.sources.map(s => [s.id, s]));
  return (r.incidents.map(i => {
    const source = sources[i.source_id];
    return `<article class="incident-card"><div class="finding-top"><span class="tag">${esc(i.id)}</span><span class="tag">${esc(i.source_type)}</span><span class="tag ${i.recency === 'Recent report' ? 'green' : 'amber'}">${esc(i.recency)}</span></div><h3>${esc(i.title)}</h3><p>${esc(i.mechanism)}</p><div class="incident-meta"><span>Published ${esc(i.publication_date)}</span><span>·</span><span>Incident ${esc(i.incident_date)}</span></div><p>Victim: ${esc(i.victim)}</p><blockquote>${esc(i.source_quote)}</blockquote><p><strong>Prerequisites:</strong> ${esc(i.prerequisites.join(' · '))}</p>${link(source.url, source.title, 'source-link')}<p class="muted">Retrieved: ${esc(source.retrieved_at)}</p></article>`;
  }).join('') || empty('No supported incident matches', 'This does not establish that the project is safe. Relevant reports may be unavailable or outside the inspected evidence.', 'search')) +
  (r.research_limitations.length ? `<h3 class="subheading">Research limitations</h3><ul class="unknown-list">${r.research_limitations.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '');
}

function renderRecommendations(a) {
  if (!a.review) return empty('Recommendations follow the evidence', 'The Security Reviewer checks incident prerequisites against repository observations, including existing defenses.', 'shield-check');
  const r = a.review;
  return `<p class="summary">${esc(r.summary)}</p>` + (r.findings.map(f => `<article class="finding-card"><div class="finding-top"><span class="tag ${f.classification === 'Supported concern' ? 'green' : 'amber'}">${esc(f.classification)}</span><span class="tag">${esc(f.impact)} impact</span><span class="tag">${esc(f.confidence)} confidence</span></div><h3>${esc(f.title)}</h3><p>${esc(f.reasoning)}</p><dl><dt>Attack prerequisite</dt><dd>${esc(f.prerequisite)}</dd><dt>Counterevidence</dt><dd>${esc(f.counterevidence)}</dd><dt>Recommended action</dt><dd>${esc(f.action)}</dd><dt>How to verify</dt><dd>${esc(f.verification)}</dd><dt>Still unknown</dt><dd>${esc(f.missing_information.join(' · ') || 'None identified within this evidence.')}</dd></dl><div class="citation-links">${evidenceLinks(f.evidence_ids)}${f.incident_ids.map(id => `<a href="#" data-incident="${esc(id)}">${esc(id)} ${icon('arrow-up-right')}</a>`).join('')}</div></article>`).join('') || empty('No evidence-backed recommendations established', 'The reviewer could not establish a defensible repository–incident connection. This is a valid result, not a security clearance.', 'shield')) +
  (r.existing_defenses.length ? `<h3 class="subheading">Existing defenses acknowledged</h3>${r.existing_defenses.map(d => `<p class="note">${esc(d.description)}</p><div class="citation-links">${evidenceLinks(d.evidence_ids)}</div>`).join('')}` : '') +
  (r.rejected_matches.length ? `<h3 class="subheading">Connections rejected</h3>${r.rejected_matches.map(m => `<p class="note">${esc(m.incident_id)} · ${esc(m.reason)}</p>`).join('')}` : '') +
  (r.questions.length ? `<h3 class="subheading">Questions for the builder</h3><ul class="unknown-list">${r.questions.map(q => `<li>${esc(q)}</li>`).join('')}</ul>` : '');
}

function renderEvidence(a) {
  if (!a.repository) return empty('Evidence will appear here', 'Commit-pinned file references, exact code excerpts, coverage details, and validation results stay available throughout the review.', 'file');
  const observations = a.profile?.observations || [];
  return `<div class="report-toolbar"><a class="button" href="/api/jobs/${currentId}/artifacts">${icon('download')}Download all artifacts</a></div><p class="note">Excerpts are checked against inspected, redacted source text. Passage integrity does not independently prove the model’s interpretation.</p>` + observations.map(o => `<article class="evidence-card" id="evidence-${esc(o.id)}"><div class="evidence-header"><span class="tag">${esc(o.id)}</span><strong>${esc(o.claim)}</strong></div><p>${link(o.url, `${o.path}:${o.start_line}–${o.end_line}`)} · ${esc(o.kind)}</p><pre>${esc(o.quote)}</pre></article>`).join('') +
    `<h3 class="subheading">Inspected files</h3>${a.repository.files.map(f => `<p class="note">${link(f.url, f.path)}${f.truncated ? ' · truncated' : ''}</p>`).join('')}` +
    (a.repository.skipped.length ? `<details><summary class="subheading">Skipped files (${a.repository.skipped.length} listed)</summary><ul class="unknown-list">${a.repository.skipped.map(s => `<li>${esc(s.path)} — ${esc(s.reason)}</li>`).join('')}</ul></details>` : '') +
    (a.validation ? `<h3 class="subheading">Validation</h3><ul class="unknown-list">${a.validation.checks.map(c => `<li>${esc(c)}</li>`).join('')}</ul><p class="note">${esc(a.validation.model)} · ${esc(a.validation.model_calls)} model calls · ${esc(a.validation.tokens)} total tokens</p>${a.validation.warnings.map(w => `<p class="note">${esc(w)}</p>`).join('')}` : '');
}

function renderReport() {
  if (!current?.report) return empty('Your report is being assembled', 'The cited Markdown report becomes available after the evidence checks finish.', 'file');
  return `<div class="report-summary"><h3>${current.status === 'partial' ? 'Report ready with limitations' : 'Your review is ready'}</h3><p>Review the evidence, verify open questions, and share the Markdown with your team.</p></div><div class="report-toolbar"><a class="button primary" href="/api/jobs/${currentId}/report">${icon('download')}Download Markdown</a><button class="button" id="copy-report">${icon('copy')}Copy report</button><a class="button" href="/api/jobs/${currentId}/artifacts">Evidence JSON</a></div><pre class="report-raw">${esc(current.report)}</pre>`;
}

function renderResults() {
  const a = current?.artifacts || {};
  const html = {overview: () => renderOverview(a), incidents: () => renderIncidents(a), recommendations: () => renderRecommendations(a), evidence: () => renderEvidence(a), report: renderReport}[activeTab]();
  const el = $('result-content');
  const scroll = el.scrollTop; el.innerHTML = html; el.scrollTop = scroll;
  $('copy-report')?.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(current.report); showToast('Markdown copied to clipboard'); }
    catch { showToast('Clipboard unavailable. Use Download Markdown.'); }
  });
}

function renderJob() {
  const a = current?.artifacts || {}, active = current && !terminal.has(current.status);
  document.body.classList.toggle('has-review', Boolean(current));
  $('review-title').textContent = current ? current.mode === 'demo' ? 'Preview service · offline example' : current.repository_url.replace('https://github.com/', '') : 'Your next review starts here';
  $('job-state').textContent = current ? ({queued:'In queue',running:'In progress',cancelling:'Cancelling',completed:'Review complete',partial:'Complete · limitations',failed:'Analysis stopped',cancelled:'Cancelled'}[current.status]) : 'Ready when you are';
  $('job-state').className = `job-state ${current?.status || ''}`;
  $('example-banner').hidden = current?.mode !== 'demo';
  $('job-error').hidden = !current?.error; $('job-error').textContent = current?.error || '';
  $('job-meta').hidden = !current;
  $('job-meta').innerHTML = a.repository ? `${link(a.repository.url, current.mode === 'demo' ? 'Synthetic repository' : 'View on GitHub')}<span>·</span><span>commit ${esc(a.repository.commit.slice(0, 12))}</span><span>·</span><span>${esc(current.days)}-day publication window</span>` : current ? `<span>Analysis ${esc(current.id.slice(0, 8))}</span><span>·</span><span>${esc(current.days)}-day publication window</span>` : '';
  document.querySelectorAll('.agent-card').forEach(el => {
    const status = current?.stages[el.dataset.stage] || 'queued';
    el.className = `agent-card ${status}`;
    el.querySelector('.stage-indicator').setAttribute('aria-label', status);
    el.querySelector('.agent-status').textContent = status === 'queued' ? 'WAITING' : status.toUpperCase();
    el.title = `${stageNames[el.dataset.stage]}: ${status}`;
  });
  $('cancel-button').hidden = !active;
  $('cancel-button').disabled = current?.status === 'cancelling';
  $('activity-dot').classList.toggle('running', !!active);
  $('preparation-status').hidden = !current;
  $('preparation-status').textContent = current ? `Preparation: ${current.stages.prepare} · Validation: ${current.stages.validation}` : '';
  $('incident-count').textContent = a.research ? a.research.incidents.length : '';
  $('finding-count').textContent = a.review ? a.review.findings.length : '';
  renderResults(); updateElapsed();
}

function updateElapsed() {
  if (!current) { $('elapsed').textContent = '—'; return; }
  const end = terminal.has(current.status) ? new Date(current.updated_at).getTime() : Date.now();
  const secs = Math.max(0, Math.floor((end - new Date(current.created_at).getTime()) / 1000));
  $('elapsed').textContent = `${Math.floor(secs / 60)}m ${String(secs % 60).padStart(2,'0')}s`;
}

function renderEvents() {
  const el = $('activity-log');
  if (!eventItems.length) { el.innerHTML = '<div class="activity-empty"><strong>Waiting for the worker…</strong><p>Queued reviews begin when the current job finishes.</p></div>'; return; }
  const stickToBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  el.innerHTML = eventItems.slice(-150).map(e => `<div class="activity-event"><div class="event-top"><span>${esc(stageNames[e.stage] || e.stage)}</span><time>${new Date(e.at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'})}</time></div><div class="event-title">${esc(e.title)}</div><div class="event-detail">${esc(e.detail)}</div></div>`).join('');
  if (stickToBottom) el.scrollTop = el.scrollHeight;
}

async function reloadCurrent() {
  const id = currentId;
  if (!id) return;
  try {
    const job = await api(`/api/jobs/${id}`);
    if (id !== currentId) return;
    const changed = JSON.stringify(current) !== JSON.stringify(job);
    current = job;
    if (changed) renderJob();
  } catch (error) { if (id === currentId) { $('job-error').hidden = false; $('job-error').textContent = error.message; } }
}

async function selectJob(id) {
  eventStream?.close(); clearTimeout(reloadTimer);
  currentId = id; current = null; eventItems = [];
  const u = new URL(location.href); u.searchParams.set('review', id); history.replaceState(null,'',u);
  $('activity-log').innerHTML = ''; renderEvents();
  await reloadCurrent();
  if (id !== currentId || !current) return;
  eventStream = new EventSource(`/api/jobs/${id}/events`);
  eventStream.addEventListener('activity', e => {
    if (id !== currentId) return;
    const item = JSON.parse(e.data);
    if (!eventItems.some(x => x.seq === item.seq)) { eventItems.push(item); renderEvents(); }
    clearTimeout(reloadTimer); reloadTimer = setTimeout(reloadCurrent, 150);
  });
  eventStream.addEventListener('finished', async () => {
    if (id !== currentId) return;
    eventStream.close(); await reloadCurrent(); await loadHistory();
  });
}

function historyRows(jobs) {
  return jobs.map(j => `<button class="recent-row" data-job="${esc(j.id)}">${icon(j.mode === 'demo' ? 'layers' : 'github')}<strong>${esc(j.mode === 'demo' ? 'Offline example · synthetic' : j.repository_url.replace('https://github.com/',''))}</strong><small>${new Date(j.created_at).toLocaleDateString(undefined,{month:'short', day:'numeric'})}</small><span class="job-state ${esc(j.status)}">${esc(j.status)}</span></button>`).join('');
}

async function loadHistory() {
  try { recent = await api('/api/jobs'); $('history-count').textContent = recent.length; $('recent-list').innerHTML = recent.length ? historyRows(recent.slice(0,5)) : '<p class="muted">Your completed and in-progress reviews will appear here.</p>'; }
  catch { /* Initial configuration error is reported separately. */ }
}

async function start(mode) {
  if (isSubmitting) return;
  if (!config) { $('form-error').textContent = 'The local server is not connected. Reload the page.'; $('form-error').hidden = false; return; }
  if (mode === 'live' && !config.live_ready) { showSettings(); return; }
  $('form-error').hidden = true;
  isSubmitting = true; $('start-button').disabled = true; $('demo-button').disabled = true;
  try {
    const result = await api('/api/jobs', {method:'POST', body:JSON.stringify({repository_url:$('repo-url').value.trim(), mode, days:Number($('window').value)})});
    switchTab('overview'); await selectJob(result.id); await loadHistory();
    scrollToElement(document.querySelector('#workspace'));
  } catch (error) { $('form-error').textContent = error.message; $('form-error').hidden = false; }
  finally { isSubmitting = false; $('start-button').disabled = false; $('demo-button').disabled = false; }
}

function openDialog(html, kicker = 'WORKSPACE') { $('dialog-content').innerHTML = html; $('dialog-kicker').textContent = kicker; if (!$('info-dialog').open) $('info-dialog').showModal(); }

function showSettings() {
  openDialog(`<h2>Connect live intelligence.</h2><p>The offline example works immediately. Live repository analysis uses the OpenAI Responses API with web search. Credentials stay on the server.</p><ol><li>Copy <code>.env.example</code> to <code>.env</code> in the project folder.</li><li>Set <code>OPENAI_API_KEY</code> locally. Never paste your key into this page or a chat.</li><li>Optionally set <code>GITHUB_TOKEN</code> for higher public API limits.</li><li>Restart <code>python run.py</code>, then refresh this page.</li></ol><pre>OPENAI_API_KEY=your-key-here\nOPENAI_MODEL=${esc(config?.model || 'gpt-4.1')}\nGITHUB_TOKEN=optional-read-only-token</pre><p><strong>Current status:</strong> ${config?.live_ready ? 'API key configured; provider access has not been verified.' : 'Live mode is not configured.'}</p><p>Public source excerpts are sent to the model provider during live analysis. Suspected credential lines are redacted, but redaction is not a guarantee. The server runs on your loopback address.</p>`, 'CONFIGURATION');
}

$('review-form').addEventListener('submit', e => { e.preventDefault(); start('live'); });
$('demo-button').addEventListener('click', () => start('demo'));
$('cancel-button').addEventListener('click', async () => { if (!currentId) return; try { await api(`/api/jobs/${currentId}/cancel`,{method:'POST',body:'{}'}); await reloadCurrent(); } catch (e) { showToast(e.message); } });
document.querySelectorAll('.tab').forEach(el => el.addEventListener('click', () => switchTab(el.dataset.tab)));
document.querySelector('.tabs').addEventListener('keydown', e => {
  if (!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return;
  e.preventDefault(); const tabs = [...document.querySelectorAll('.tab')]; let i = tabs.indexOf(document.activeElement);
  i = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : (i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
  tabs[i].focus(); switchTab(tabs[i].dataset.tab);
});
document.addEventListener('click', e => {
  const job = e.target.closest('[data-job]'); if (job) { $('info-dialog').close(); selectJob(job.dataset.job); scrollToElement(document.querySelector('.analysis-grid')); }
  const ev = e.target.closest('[data-evidence]'); if (ev) { e.preventDefault(); switchTab('evidence'); scrollToElement(document.getElementById(`evidence-${ev.dataset.evidence}`), 'nearest'); }
  const inc = e.target.closest('[data-incident]'); if (inc) { e.preventDefault(); switchTab('incidents'); }
});
$('settings-nav').addEventListener('click',showSettings); $('connection-status').addEventListener('click',showSettings);
$('how-nav').addEventListener('click', () => openDialog('<h2>Three roles. One evidence chain.</h2><p><strong>01 · Repository Analyst</strong><br>Reads a bounded selection of code at a fixed commit. Maps technology, security-relevant behavior, and unknowns.</p><p><strong>02 · Incident Researcher</strong><br>Searches selected primary sources, retrieves pages, and extracts documented attack mechanisms and prerequisites.</p><p><strong>03 · Security Reviewer</strong><br>Checks the connection, looks for existing defenses, and recommends concrete actions and verification steps.</p><p><strong>Then: evidence validation</strong><br>Checks quote integrity and evidence references before assembling your report. These checks do not independently prove that every AI interpretation is correct.</p><p>A shared framework does not establish a shared weakness. Incomplete evidence is labeled. No code runs and no files in the analyzed repository are changed.</p>', 'THE WORKFLOW'));
$('history-nav').addEventListener('click', async () => { await loadHistory(); openDialog(`<h2>Past reviews</h2>${recent.length ? historyRows(recent) : '<p>No reviews yet. Start with a public repository or try the offline example.</p>'}`, 'LOCAL HISTORY'); });
$('workspace-nav').addEventListener('click', () => { document.querySelector('main').scrollIntoView({behavior:'smooth'}); $('repo-url').focus(); });
$('close-dialog').addEventListener('click', () => $('info-dialog').close());
document.addEventListener('keydown', e => { if (e.key === '/' && !['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName) && !$('info-dialog').open) { e.preventDefault(); $('repo-url').focus(); } });

async function initialize() {
  renderJob();
  try {
    config = await api('/api/config');
    $('connection-status').innerHTML = `<span class="tiny-dot"></span>${config.live_ready ? 'Live mode configured' : 'Live mode needs setup'}`;
    $('connection-status').classList.toggle('needs-setup', !config.live_ready);
    await loadHistory();
    const id = new URLSearchParams(location.search).get('review');
    if (id && /^[a-f0-9]{32}$/.test(id)) await selectJob(id);
  } catch (error) { $('connection-status').textContent = 'Server unavailable'; $('form-error').textContent = error.message; $('form-error').hidden = false; }
  setInterval(() => { updateElapsed(); if (current && !terminal.has(current.status)) reloadCurrent(); }, 4000);
}
initialize();
