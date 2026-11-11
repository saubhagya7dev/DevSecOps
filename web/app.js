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
  $('report-section').hidden = false;
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

function renderStructuredDiscovery(r) {
  const advisories = (r.advisories || []).map(item => `<article class="incident-card"><span class="tag">Vulnerability advisory</span><h3>${esc(item.id)} · ${esc(item.title)}</h3><p>${esc(item.package.ecosystem)} / ${esc(item.package.name)} · ${esc(item.package.version_kind)}</p><p>${esc(item.version_assessment)}</p><p>CVSS: ${esc(item.cvss_score ?? 'Unscored')}</p><p>Identifiers: ${esc(item.identifiers.join(', ') || 'Not supplied')}</p><p>Provider-reported fixes: ${esc(item.fixed_versions.join(', ') || 'Unknown')}</p><p>Published ${esc(item.publication_date)} · Retrieved ${esc(item.retrieved_at)}</p><p>${item.provenance.map(p => link(p.url, `${p.provider} record`)).join(' · ')}</p><p class="note">An advisory is not evidence that an attack occurred or that this repository is exploitable.</p></article>`).join('');
  const techniques = (r.techniques || []).map(t => `<p>${link(t.url, `${t.id} · ${t.name}`)}</p>`).join('');
  const history = (r.historical_records || []).map(h => `<article class="incident-card"><span class="tag">Historical record</span><h3>${esc(h.id)}</h3><p>${esc(h.summary)}</p><p>Incident ${esc(h.incident_date)} · Year ${esc(h.incident_year ?? "unknown")} · Publication unknown · Retrieved ${esc(h.retrieved_at)}</p><p>${esc(h.limitation)}</p><p>${link(h.provenance, 'Official VCDB record')}</p></article>`).join('');
  const mappings = (r.attack_mappings || []).map(m => `<p class="note">${esc(m.incident_id)} · ${esc(m.status)} ${esc(m.technique_ids.join(', '))}</p>`).join('');
  const coverage = r.coverage ? `<h3 class="subheading">Discovery coverage</h3><p>${esc(r.outcome)}</p><pre>${esc(JSON.stringify(r.coverage, null, 2))}</pre>` : '';
  return (advisories ? `<h3 class="subheading">Package advisories · separate from incidents</h3>${advisories}` : '') +
    (techniques ? `<h3 class="subheading">ATT&CK candidates</h3><p class="note">Background techniques, not confirmed incidents or mappings. Unsupported mechanisms remain unmapped.</p>${techniques}${mappings}` : '') +
    (history ? `<h3 class="subheading">Historical VCDB records</h3>${history}` : '') + coverage;
}

function renderIncidents(a) {
  if (!a.research) return empty('Research has not arrived yet', 'Documented attacks and retrieved passages will appear after the Incident Researcher completes its work.', 'search');
  const r = a.research, sources = Object.fromEntries(r.sources.map(s => [s.id, s]));
  const failed = r.status === 'failed' || r.research_limitations.some(x => x.startsWith('Incident research incomplete:'));
  const cards = kind => r.incidents.filter(i => i.source_type === kind).map(i => {
    const source = sources[i.source_id];
    const support = (i.supporting_sources || []).filter(x => x.source_id !== i.source_id && sources[x.source_id]).map(x => `<details><summary>Additional source: ${esc(x.source_id)}</summary><p>${link(sources[x.source_id].url, sources[x.source_id].title)}</p><blockquote>${esc(x.source_quote)}</blockquote></details>`).join('');
    return `<article class="incident-card"><div class="finding-top"><span class="tag">${esc(i.id)}</span><span class="tag">${esc(i.source_type)}</span><span class="tag ${i.recency === 'Recent report' ? 'green' : 'amber'}">${esc(i.recency)}</span></div><h3>${esc(i.title)}</h3><p>${esc(i.mechanism)}</p><div class="incident-meta"><span>Published ${esc(i.publication_date)}</span><span>·</span><span>Incident ${esc(i.incident_date)}</span></div><p>Victim: ${esc(i.victim)}</p><blockquote>${esc(i.source_quote)}</blockquote><p><strong>Prerequisites:</strong> ${esc(i.prerequisites.join(' · '))}</p>${link(source.url, source.title, 'source-link')}<p class="muted">Retrieved: ${esc(source.retrieved_at)}</p>${support}</article>`;
  }).join('');
  const groups = [['Documented attacks and observed campaigns', 'observed attack'], ['Narrative vulnerability advisories', 'vulnerability advisory'], ['Background mechanisms', 'background guidance']].map(([label, kind]) => { const html = cards(kind); return html ? `<h3 class="subheading">${esc(label)}</h3>${html}` : ''; }).join('');
  return (groups || empty(failed ? 'Incident research failed' : 'No supported incident matches', failed ? 'Retrieval, provider access, or resource limits prevented this investigation from completing. This is not a finding that no attacks exist. Inspect the saved error and coverage below.' : 'This does not establish that the project is safe. Relevant reports may be unavailable or outside the inspected evidence.', 'search')) +
  (r.research_limitations.length ? `<h3 class="subheading">Research limitations</h3><ul class="unknown-list">${r.research_limitations.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '') + renderStructuredDiscovery(r);
}

function renderRecommendations(a) {
  if (!a.review) return empty('Recommendations follow the evidence', 'The Security Reviewer checks incident prerequisites against repository observations, including existing defenses.', 'shield-check');
  const r = a.review;
  const researchFailed = a.research?.status === 'failed' || a.research?.research_limitations.some(x => x.startsWith('Incident research incomplete:'));
  if (r.status === 'skipped' || (researchFailed && !a.research?.incidents?.length && !r.findings.length)) return empty('Security review was not performed', researchFailed ? 'Incident research failed, so the reviewer had no validated incident evidence. Fix the research error and start a new run. This result says nothing about repository safety.' : r.summary, 'shield') + (r.reason ? `<p class="note">${esc(r.reason)}</p>` : '');
  return `<p class="summary">${esc(r.summary)}</p>` + (r.findings.map(f => `<article class="finding-card"><div class="finding-top"><span class="tag ${f.classification === 'Supported concern' ? 'green' : 'amber'}">${esc(f.classification)}</span><span class="tag">${esc(f.impact)} impact</span><span class="tag">${esc(f.confidence)} confidence</span></div><h3>${esc(f.title)}</h3><p>${esc(f.reasoning)}</p><dl><dt>Attack prerequisite</dt><dd>${esc(f.prerequisite)}</dd><dt>Counterevidence</dt><dd>${esc(f.counterevidence)}</dd><dt>Recommended action</dt><dd>${esc(f.action)}</dd><dt>How to verify</dt><dd>${esc(f.verification)}</dd>${f.prerequisite_assessments?.length ? `<dt>Prerequisite assessments</dt><dd>${f.prerequisite_assessments.map(a => `${esc(a.state)}: ${esc(a.prerequisite)} — ${esc(a.reason)}`).join('<br>')}</dd>` : ''}<dt>Still unknown</dt><dd>${esc(f.missing_information.join(' · ') || 'None identified within this evidence.')}</dd></dl><div class="citation-links">${evidenceLinks(f.evidence_ids)}${f.incident_ids.map(id => `<a href="#" data-incident="${esc(id)}">${esc(id)} ${icon('arrow-up-right')}</a>`).join('')}</div></article>`).join('') || empty('No evidence-backed recommendations established', 'The reviewer could not establish a defensible repository–incident connection. This is a valid result, not a security clearance.', 'shield')) +
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
  return `<div class="report-summary"><h3>${current.status === 'partial' ? 'Report ready with limitations' : 'Your review is ready'}</h3><p>Review the evidence, verify open questions, and share the Markdown with your team.</p></div><div class="report-toolbar"><a class="button primary" href="/api/jobs/${currentId}/report">${icon('download')}Download Markdown</a><button class="button" id="copy-report">${icon('copy')}Copy report</button><a class="button" href="/api/jobs/${currentId}/artifacts">Evidence JSON</a></div><label class="report-scroll-toggle"><input id="report-sync" type="checkbox" checked>Sync scrolling</label><div class="report-split"><section class="report-pane"><div class="report-pane-bar">MARKDOWN SOURCE <span>Read-only · ${current.report.split('\n').length} lines</span></div><pre id="report-source" class="report-source" tabindex="0" aria-label="Report Markdown source">${current.report.split('\n').map(line=>`<span class="source-line">${esc(line)||' '}</span>`).join('')}</pre></section><section class="report-pane"><div class="report-pane-bar">PREVIEW <span>Rendered Markdown</span></div><article id="report-preview" class="markdown-preview" tabindex="0" aria-label="Rendered report preview">${ReportMarkdown.render(current.report)}</article></section></div>`;
}

function renderResults() {
  const a = current?.artifacts || {};
  const html = {overview: () => renderOverview(a), incidents: () => renderIncidents(a), recommendations: () => renderRecommendations(a), evidence: () => renderEvidence(a), report: renderReport}[activeTab]();
  const el = $('result-content');
  const scroll = el.scrollTop; el.innerHTML = html; el.scrollTop = scroll;
  const source = $('report-source'), preview = $('report-preview');
  if (source && preview) {
    let scheduled = false;
    for (const [from, to] of [[source, preview], [preview, source]]) {
      from.addEventListener('scroll', () => {
        if (scheduled || !$('report-sync').checked) return;
        scheduled = true;
        const range = from.scrollHeight - from.clientHeight;
        to.scrollTop = range > 0 ? from.scrollTop / range * (to.scrollHeight - to.clientHeight) : 0;
        requestAnimationFrame(() => { scheduled = false; });
      }, {passive:true});
    }
  }
  $('copy-report')?.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(current.report); showToast('Markdown copied to clipboard'); }
    catch { showToast('Clipboard unavailable. Use Download Markdown.'); }
  });
}

function renderJob() {
  const a = current?.artifacts || {}, active = current && !terminal.has(current.status);
  document.body.classList.toggle('has-review', Boolean(current));
  $('review-title').textContent = current ? current.mode === 'demo' ? 'Preview service · offline example' : current.repository_url.replace('https://github.com/', '') : 'Your next review starts here';
  $('job-state').textContent = current ? ({queued:'In queue',running:'In progress',cancelling:'Cancelling',completed:'Review complete',partial:'Incomplete · limitations',failed:'Analysis stopped',cancelled:'Cancelled'}[current.status]) : 'Ready when you are';
  $('job-state').className = `job-state ${current?.status || ''}`;
  $('example-banner').hidden = current?.mode !== 'demo';
  $('job-error').hidden = !current?.error; $('job-error').textContent = current?.error || '';
  $('job-meta').hidden = !current;
  $('job-meta').innerHTML = a.repository ? `${link(a.repository.url, current.mode === 'demo' ? 'Synthetic repository' : a.repository.name)}<span>·</span><span>commit ${esc(a.repository.commit.slice(0, 12))}</span><span>·</span><span>${esc(current.days)}-day publication window</span>` : current ? `<span>Analysis ${esc(current.id.slice(0, 8))}</span><span>·</span><span>${esc(current.days)}-day publication window</span>` : '';
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
  renderResults(); renderGraph(); renderInspector(); renderExperience(); updateElapsed();
}

function updateElapsed() {
  if (!current) { $('elapsed').textContent = '—'; return; }
  const end = terminal.has(current.status) ? new Date(current.updated_at).getTime() : Date.now();
  const secs = Math.max(0, Math.floor((end - new Date(current.created_at).getTime()) / 1000));
  $('elapsed').textContent = `${String(Math.floor(secs / 60)).padStart(2,'0')}:${String(secs % 60).padStart(2,'0')}`;
  renderLiveStatus();
}

function renderEvents() {
  renderGraph(); renderLiveStatus();
  const el = $('activity-log');
  if (!eventItems.length) { el.innerHTML = current && terminal.has(current.status) ? '<div class="activity-empty"><strong>No activity events retained for this saved review.</strong><p>Its evidence and report remain available.</p></div>' : '<div class="activity-empty"><strong>Waiting for the worker…</strong><p>Queued reviews begin when the current job finishes.</p></div>'; return; }
  const stickToBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  el.innerHTML = eventItems.slice(-150).map(e => `<div class="activity-event"><div class="event-top"><span>${esc(stageNames[e.stage] || e.stage)}</span><time>${new Date(e.at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'})}</time></div><div class="event-title">${esc(e.title)}</div><div class="event-detail">${esc(e.detail)}</div></div>`).join('');
  if (stickToBottom) el.scrollTop = el.scrollHeight;
}

const loadJobUpdate = JobUpdates.createLoader(api);

async function reloadCurrent() {
  const id = currentId;
  if (!id) return;
  try {
    const job = await loadJobUpdate(id, current);
    if (!JobUpdates.shouldApply(currentId, current, job)) return;
    current = job;
    renderJob();
  } catch (error) { if (id === currentId) { $('job-error').hidden = false; $('job-error').textContent = error.message; } }
}

async function selectJob(id) {
  eventStream?.close(); clearTimeout(reloadTimer);
  document.body.classList.remove('show-input');
  currentId = id; current = null; eventItems = []; selectedNode = null; graphSignature = ''; streamConnected = false; graphView?.reset();
  $('report-section').hidden = true;
  const u = new URL(location.href); u.searchParams.set('review', id); history.replaceState(null,'',u);
  $('activity-log').innerHTML = ''; renderEvents();
  await reloadCurrent();
  if (id !== currentId || !current) return;
  eventStream = new EventSource(`/api/jobs/${id}/events`);
  eventStream.addEventListener('open', () => { if(id === currentId){streamConnected = true; renderLiveStatus();} });
  eventStream.addEventListener('error', () => { if(id === currentId){streamConnected = false; renderLiveStatus();} });
  eventStream.addEventListener('activity', e => {
    if (id !== currentId) return;
    const item = JSON.parse(e.data);
    if (!eventItems.some(x => x.seq === item.seq)) { eventItems.push(item); renderEvents(); }
    clearTimeout(reloadTimer); reloadTimer = setTimeout(reloadCurrent, 150);
  });
  eventStream.addEventListener('finished', async () => {
    if (id !== currentId) return;
    eventStream.close(); streamConnected = false; await reloadCurrent(); await loadHistory();
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
    activeTab = 'overview'; switchTab('overview'); $('report-section').hidden = true; await selectJob(result.id); await loadHistory();
    scrollToElement($('progress-title'));
  } catch (error) { $('form-error').textContent = error.message; $('form-error').hidden = false; }
  finally { isSubmitting = false; $('start-button').disabled = false; $('demo-button').disabled = false; }
}

function openDialog(html, kicker = 'WORKSPACE') { $('dialog-content').innerHTML = html; $('dialog-kicker').textContent = kicker; if (!$('info-dialog').open) $('info-dialog').showModal(); }

function showSettings() {
  const roles = Object.entries(config?.roles || {}).map(([role, setting]) => `<li><strong>${esc(role)}</strong> · ${esc(setting.provider)} · <code>${esc(setting.model)}</code></li>`).join('');
  const missing = (config?.missing_credentials || []).map(esc).join(', ');
  openDialog(`<h2>Connect live intelligence.</h2><p>Gemini analyzes the repository. Python discovers advisories and original reports; Qwen on Groq interprets selected passages within quota limits. GPT OSS on Groq reviews the evidence. Credentials stay on the server.</p><ul>${roles}</ul><p><strong>Researcher token allowance:</strong> ${esc(config?.researcher_token_budget ?? 1000)}, including instructions, schema, and reserved output. Change <code>RESEARCHER_TOKEN_BUDGET</code> only after verifying your provider quota. Optional VCDB discovery is ${config?.vcdb_enabled ? "enabled" : "disabled"}.</p><ol><li>For a new installation, copy <code>.env.example</code> to <code>.env</code>. Merge these settings into an existing file.</li><li>Set <code>GEMINI_API_KEY</code>, <code>GROQ_API_KEY</code>, and <code>TAVILY_API_KEY</code> locally. Never paste keys into this page or a chat.</li><li>Optionally set <code>GITHUB_TOKEN</code> for higher public API limits.</li><li>Restart <code>python run.py</code>, then refresh this page.</li></ol><button class="button" data-manage-storage>Manage history &amp; research cache</button><p><strong>Current status:</strong> ${config?.live_ready ? 'All credentials configured; provider access has not been verified.' : `Missing: ${missing || 'configuration unavailable'}.`}</p><p>Public source excerpts are sent to Gemini and Groq. Generated search queries are sent to Tavily. Suspected credential lines are redacted, but redaction is not a guarantee. The offline example needs no keys.</p>`, 'CONFIGURATION');
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
  const job = e.target.closest('[data-job]'); if (job) { $('info-dialog').close(); selectJob(job.dataset.job); scrollToElement($('progress-title')); }
  const ev = e.target.closest('[data-evidence]'); if (ev) { e.preventDefault(); selectGraphNode('obs:'+ev.dataset.evidence); switchTab('evidence'); scrollToElement(document.getElementById(`evidence-${ev.dataset.evidence}`), 'nearest'); }
  const inc = e.target.closest('[data-incident]'); if (inc) { e.preventDefault(); switchTab('incidents'); }
});
$('settings-nav').addEventListener('click',showSettings); $('connection-status').addEventListener('click',showSettings);
$('how-nav').addEventListener('click',()=>showWorkflow());
$('history-nav').addEventListener('click', async () => { await loadHistory(); openDialog(`<h2>Past reviews</h2>${recent.length ? historyRows(recent) : '<p>No reviews yet. Start with a public repository or try the offline example.</p>'}`, 'LOCAL HISTORY'); });
$('workspace-nav').addEventListener('click', () => { $('report-section').hidden = true; scrollToElement($('workspace')); });
$('close-dialog').addEventListener('click', () => $('info-dialog').close());
document.addEventListener('keydown', e => { if (e.key === '/' && !['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName) && !$('info-dialog').open) { e.preventDefault(); $('repo-url').focus(); } });

// Small, event-driven workspace view. Glow is visual; graph relationships come from artifacts.
let selectedNode = null, graphSignature = '', graphModel = {nodes:[],edges:[],groups:[]};
let graphMode = 'structure', streamConnected = false;
let graphView=null;
const graphSettings={query:'',mode:'structure',inspected:false,orphans:true,minScore:0,severities:['Critical','High','Medium','Low','Clean','Unscored'],colorMode:'architecture',nodeScale:1,linkWidth:1,labels:'all',pulses:false,gravity:.007,charge:5000,distance:90,damping:.82};
function renderGraph() {
  if(typeof RepoGraph==='undefined'||!RepoGraph.CanvasView){$('graph-coverage').textContent='Refresh the page or restart the local server to load the graph.';return;}
  if(!graphView)graphView=new RepoGraph.CanvasView($('repo-graph'),selectGraphNode,node=>{
    $('graph-tooltip').hidden=!node;
    $('graph-tooltip').textContent=node?`${node.path||node.label} / ${node.type} / ${node.cvss!==null&&node.cvss!==undefined?'CVSS '+node.cvss:'Unscored'}`:'';
  });
  const artifacts=current?.artifacts||{};
  const signature=JSON.stringify([currentId,artifacts,eventItems.filter(e=>e.title==='Read repository file').map(e=>e.detail)]);
  if(signature!==graphSignature){
    graphModel=RepoGraph.build(artifacts,eventItems);graphSignature=signature;
    if(!graphModel.nodes.some(n=>n.id===selectedNode))selectedNode=graphModel.nodes.find(n=>n.type==='file'&&n.inspected)?.id||graphModel.nodes[0]?.id;
  }
  Object.assign(graphSettings,{mode:graphMode,query:$('graph-search').value,inspected:$('inspected-only').checked});
  const visible=RepoGraph.filter(graphModel,graphSettings);
  graphView.update(graphSettings,selectedNode);graphView.setModel(visible);
  $('graph-empty').hidden=visible.nodes.length>0;
  $('graph-empty').querySelector('h3').textContent=graphModel.nodes.length?'No nodes match these filters.':'A repository becomes a map.';
  $('graph-empty').querySelector('p').textContent=graphModel.nodes.length?'Adjust severity, score, orphan, or keyword filters.':'Start an investigation to explore files, dependencies, and the evidence connecting them.';
  $('graph-coverage').textContent=graphModel.nodes.length?`${visible.nodes.length} visible · ${graphModel.read} files read${graphModel.omitted?' · '+graphModel.omitted+' tree entries omitted':''}`:'Waiting for repository';
  const legend=graphSettings.colorMode==='heatmap'?Object.entries(RepoGraph.heat):graphSettings.colorMode==='layers'?[...new Set(visible.nodes.map(n=>n.layer))].map(name=>[name,RepoGraph.layerColor(name)]):graphModel.groups.map((g,i)=>[g,RepoGraph.colors[i%6]]);
  $('graph-legend').innerHTML=legend.map(([name,color])=>`<span class="legend-item"><svg viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="${color}"/></svg>${esc(name)}</span>`).join('');
  $('graph-node-list').innerHTML=visible.nodes.map(n=>`<button data-node="${esc(n.id)}">${esc(n.path||n.label)} / ${esc(n.type)}</button>`).join('');
  $('node-count').textContent=visible.nodes.length;
  document.querySelectorAll('[data-severity-count]').forEach(el=>{el.textContent=graphModel.nodes.filter(n=>RepoGraph.severity(RepoGraph.validScore(n.cvss))===el.dataset.severityCount).length;});
  const count=visible.edges.filter(e=>e.finding).length;
  $('path-pulse-note').textContent=`${count} candidate evidence link(s). Pulses do not establish an exploitable attack path. Reduced-motion preference disables pulses.`;
}
function selectGraphNode(id){selectedNode=id;renderGraph();renderInspector();}
function codePreview(file, observation){
  const start=observation?.start_line||1;
  const lines=file?file.content.split('\n').slice(Math.max(0,start-3),observation?Math.min(observation.end_line+2,start+60):15):observation?.quote?.split('\n')||[];
  const offset=file?Math.max(1,start-2):start;
  return lines.length?`<div class="code-caption"><span>${esc(file?.path||observation.path)}</span><span>L${start}${observation?'–L'+observation.end_line:''}</span></div><pre class="code-lines">${lines.map((line,i)=>`<span>${offset+i}</span>${esc(line)}`).join('\n')}</pre>`:'<p>This file is in the returned tree but its content has not been inspected.</p>';
}
function renderInspector(){
  const n=graphModel.nodes.find(n=>n.id===selectedNode),a=current?.artifacts||{};
  if(!n){$('inspector-content').innerHTML='<div class="inspector-empty"><h3>Every connection has a source.</h3><p>Select a graph node to inspect its file, cited observations, and any associated external evidence.</p><p>Node colors distinguish groups, not risk.</p></div>';return;}
  if(n.advisory){
    const v=n.advisory,score=RepoGraph.validScore(n.cvss);
    $('inspector-content').innerHTML=`<div class="inspector-chain">${esc(v.identifiers?.join(' · ')||v.id)}</div><section class="inspector-section"><h3><span class="step-box coral">01</span>Vulnerability advisory</h3><strong>${esc(v.title)}</strong><p>${esc(v.package?.ecosystem)} / ${esc(v.package?.name)}</p><p>${esc(v.version_assessment)}</p></section><section class="inspector-section"><h3><span class="step-box violet">02</span>Published CVSS</h3><p>${score===null?'Unscored / no published numeric score retained.':`CVSS ${score} / ${esc(RepoGraph.severity(score))}`}</p>${(v.cvss_ratings||[]).map(r=>`<p>${esc(r.provider)} / v${esc(r.version)} / ${esc(r.score)}<br><code>${esc(r.vector)}</code></p>`).join('')}<p>${(v.provenance||[]).map(p=>link(p.url,p.provider+' record')).join(' · ')}</p></section><section class="inspector-section"><h3><span class="step-box">03</span>Applicability remains unverified</h3><p>${esc(v.limitation||'An advisory does not establish an observed attack or target exposure.')}</p><p>Provider-reported fixes: ${esc((v.fixed_versions||[]).join(', ')||'Unknown')}</p></section><div class="inspector-actions"><button data-output="incidents">All research ↗</button></div>`;
    return;
  }
  const observations=a.profile?.observations||[],o=n.observation;
  const selectedObservations=o?[o]:n.type==='file'?observations.filter(x=>x.path===n.path):n.type==='technology'?observations.filter(x=>n.technology.evidence_ids.includes(x.id)):[];
  const ids=new Set(selectedObservations.map(x=>x.id));
  const findings=(a.review?.findings||[]).filter(f=>f.evidence_ids.some(e=>ids.has(e))||n.incident&&f.incident_ids.includes(n.incident.id));
  const incidentIds=new Set(findings.flatMap(f=>f.incident_ids));
  if(n.incident)incidentIds.add(n.incident.id);
  const incidents=(a.research?.incidents||[]).filter(i=>incidentIds.has(i.id));
  const path=o?.path||n.path, file=(a.repository?.files||[]).find(f=>f.path===path);
  const children=n.type==='directory'?graphModel.nodes.filter(x=>x.group===n.group&&x.type==='file'):[];
  $('inspector-content').innerHTML=`<div class="inspector-chain">${esc(path||n.label)}${ids.size?' / '+esc([...ids].join(' · ')):''}</div>
    <section class="inspector-section"><h3><span class="step-box coral">01</span>Repository observation</h3>${n.type==='source'?'<p>External source selected. Repository associations appear only when a finding cites both sides.</p>':`<strong>${esc(n.label)}</strong>${n.type==='directory'?`<p>Directory membership, derived from returned repository paths.</p><div class="inspection-links">${children.slice(0,20).map(c=>`<button data-node="${esc(c.id)}">${esc(c.label)}</button>`).join('')}</div>`:selectedObservations.map(x=>`<p>${esc(x.claim)}</p><div class="source-kind">${esc(x.id)} / ${esc(x.kind)} / L${x.start_line}–L${x.end_line}</div>`).join('')||'<p>No verified observations for this selection yet.</p>'}${path?codePreview(file,selectedObservations[0]):''}`}</section>
    <section class="inspector-section"><h3><span class="step-box violet">02</span>External evidence</h3>${incidents.length?incidents.map(i=>{const s=(a.research?.sources||[]).find(x=>x.id===i.source_id);return `<div class="source-kind">${esc(i.id)} / ${esc(i.source_type)}</div><p>${esc(i.title)}</p><blockquote>${esc(i.source_quote)}</blockquote>${s?link(s.url,s.title):''}<p class="note">${esc(i.recency||'Date unverified')} · Applicability requires reviewer assessment.</p>`;}).join(''):'<p>No external evidence has been linked to this selection. A shared technology alone does not establish exposure.</p>'}</section>
    <section class="inspector-section"><h3><span class="step-box">03</span>Reviewer assessment</h3>${findings.length?findings.map(f=>`<div class="source-kind">${esc(f.id)} / ${esc(f.classification)}</div><p><strong>${esc(f.title)}</strong></p><p>${esc(f.action)}</p><p>Verify: ${esc(f.verification)}</p>${f.missing_information?.length?`<p>Unknown: ${esc(f.missing_information.join('; '))}</p>`:''}`).join(''):`<p>${a.review?'No accepted recommendation is linked to this selection.':'Reviewer assessment is pending. Deployment exposure remains unknown.'}</p>`}<p id="inspector-live-status"></p></section>
    <div class="inspector-actions"><button data-output="evidence">All evidence ↗</button><button data-output="recommendations">Recommendations ↗</button></div>`;
  renderLiveStatus();
}
function renderLiveStatus(){
  const running=current&&!terminal.has(current.status), latest=eventItems.at(-1);
  const stage=Object.keys(stageNames).find(s=>current?.stages[s]==='running');
  const operation=latest?.title==='Agent working'?({analyst:'Analyzing repository…',researcher:'Interpreting source evidence…',reviewer:'Assessing evidence and prerequisites…'}[stage]||latest.title):latest?.title==='Stage started'?latest.detail:latest?.title==='Read repository file'?'Reading '+latest.detail:latest?.title;
  const status=running?(operation||'Waiting for the worker…'):current?$('job-state').textContent:'No investigation running.';
  const live=Boolean(running&&streamConnected);
  $('operation-status').textContent=status;
  $('operation-status').classList.toggle('luminous',live);
  $('following-stage').textContent='/ '+(stage?stageNames[stage]:current?'Investigation saved':'Awaiting repository');
  $('stream-state').textContent=running?(streamConnected?'Connected':'Reconnecting…'):current?'Saved activity':'Not connected';
  $('live-focus-agent').textContent=stage?stageNames[stage]:current?'Saved investigation':'Waiting for a repository';
  $('live-focus-operation').textContent=status;
  $('live-focus-operation').classList.toggle('luminous',live);
  renderExperience();
  const age=latest?Math.max(0,Math.floor((Date.now()-Date.parse(latest.at))/1000)):null;
  $('event-age').textContent=running&&age!==null?`Last update ${age}s ago`:'';
  $('reviewer-state').textContent=(current?.stages.reviewer||'waiting').toUpperCase();
  $('reviewer-detail').textContent=current?.artifacts?.review?.summary || (current?.stages.reviewer==='running'?'Review request in progress. Awaiting the next provider update.':'Starts after evidence extraction and citation checks.');
  $('view-report').disabled=!current?.report;
  const label=$('inspector-live-status');if(label){label.textContent=stage==='reviewer'&&running?status:'';label.classList.toggle('luminous',live&&stage==='reviewer');}
  const lastTitle=$('activity-log').lastElementChild?.querySelector('.event-title');lastTitle?.classList.toggle('luminous',live);
}
$('new-investigation').addEventListener('click',beginNewInvestigation);
$('graph-search').addEventListener('input',()=>{$('control-query').value=$('graph-search').value;renderGraph();});
$('inspected-only').addEventListener('change',renderGraph);
['structure','evidence'].forEach(mode=>$('graph-'+mode).addEventListener('click',()=>{graphMode=mode;['structure','evidence'].forEach(m=>{$('graph-'+m).classList.toggle('active',mode===m);$('graph-'+m).setAttribute('aria-pressed',String(mode===m));});renderGraph();}));
$('zoom-in').addEventListener('click',()=>graphView?.zoom(1.25));
$('zoom-out').addEventListener('click',()=>graphView?.zoom(.8));
$('zoom-fit').addEventListener('click',()=>graphView?.fit());
document.addEventListener('click',e=>{const node=e.target.closest('button[data-node]');if(node)selectGraphNode(node.dataset.node);const output=e.target.closest('[data-output]');if(output){switchTab(output.dataset.output);scrollToElement($('report-section'));}});
$('severity-groups').innerHTML=graphSettings.severities.map(name=>`<label class="severity-row"><input type="checkbox" data-severity="${name}" checked><span>${name==='Clean'?'Clean / CVSS 0':name}</span><output data-severity-count="${name}">0</output></label>`).join('');
$('severity-groups').addEventListener('change',()=>{graphSettings.severities=[...document.querySelectorAll('[data-severity]:checked')].map(el=>el.dataset.severity);renderGraph();});
$('control-query').addEventListener('input',()=>{$('graph-search').value=$('control-query').value;renderGraph();});
$('show-orphans').addEventListener('change',()=>{graphSettings.orphans=$('show-orphans').checked;renderGraph();});
$('graph-color-mode').addEventListener('change',()=>{graphSettings.colorMode=$('graph-color-mode').value;renderGraph();});
$('graph-labels').addEventListener('change',()=>{graphSettings.labels=$('graph-labels').value;renderGraph();});
$('path-pulses').addEventListener('change',()=>{graphSettings.pulses=$('path-pulses').checked;renderGraph();});
[['min-cvss','minScore'],['node-scale','nodeScale'],['link-width','linkWidth'],['gravity','gravity'],['charge','charge'],['link-distance','distance'],['damping','damping']].forEach(([id,key])=>{
  $(id).addEventListener('input',()=>{graphSettings[key]=Number($(id).value);$(id+'-value').textContent=$(id).value;renderGraph();});
});
$('reset-forces').addEventListener('click',()=>{[['gravity',.007],['charge',5000],['link-distance',90],['damping',.82]].forEach(([id,value])=>{$(id).value=value;$(id).dispatchEvent(new Event('input'));});});
function selectControlTab(tab){
  document.querySelectorAll('[data-control-tab]').forEach(el=>{const active=el.dataset.controlTab===tab;el.setAttribute('aria-selected',String(active));el.tabIndex=active?0:-1;$('control-'+el.dataset.controlTab).hidden=!active;});
}
document.querySelectorAll('[data-control-tab]').forEach(el=>el.addEventListener('click',()=>selectControlTab(el.dataset.controlTab)));
document.querySelector('.control-tabs').addEventListener('keydown',e=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
  e.preventDefault();const tabs=[...document.querySelectorAll('[data-control-tab]')],i=tabs.indexOf(document.activeElement);
  const target=tabs[e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length];target.focus();selectControlTab(target.dataset.controlTab);
});
$('close-graph-controls').addEventListener('click',()=>{$('graph-controls').open=false;$('graph-controls').querySelector('summary').focus();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('graph-controls').open){$('graph-controls').open=false;$('graph-controls').querySelector('summary').focus();}});
document.addEventListener('click',e=>{if($('graph-controls').open&&!e.target.closest('#graph-controls'))$('graph-controls').open=false;});
$('view-report').addEventListener('click',()=>{switchTab('report');scrollToElement($('report-section'));});
$('close-results').addEventListener('click',()=>{$('report-section').hidden=true;});
setInterval(()=>{if(current&&!terminal.has(current.status))updateElapsed();},1000);


const flowSteps=[
  {id:'prepare',name:'Read snapshot',title:'Read a bounded, pinned repository snapshot',input:'One public GitHub URL',work:'Python reads selected source files at a fixed commit. No repository code is executed.',output:'Inspected files, source paths, and coverage limits.',tab:'evidence'},
  {id:'analyst',name:'Repository Analyst',title:'Turn inspected code into cited observations',input:'Numbered source files and repository structure',work:'The analyst maps components, technologies, behavior, and observed defenses. Exact quotations and line ranges are checked locally.',output:'Verified observations, a technology profile, and explicit unknowns.',tab:'overview'},
  {id:'researcher',name:'Incident Researcher',title:'Retrieve original reports and ground the research',input:'Observed technology and attack-mechanism questions',work:'Python queries official advisories and Tavily, fetches primary reports, and ranks passages. The researcher interprets selected text within the configured model allowance.',output:'External records and source passages; advisories and background remain distinct.',tab:'incidents'},
  {id:'reviewer',name:'Security Reviewer',title:'Check whether attack prerequisites connect to this code',input:'Repository observations and retrieved external evidence',work:'The reviewer compares prerequisites, existing defenses, counterevidence, and missing deployment context. Shared technology alone is insufficient.',output:'Preventive recommendations, verification questions, or rejected matches.',tab:'recommendations'},
  {id:'validation',name:'Validate & report',title:'Make the evidence trail reviewable',input:'Agent outputs, quote checks, and evidence references',work:'Python validates references and assembles the cited Markdown report. A report can finish with limitations or contain zero accepted recommendations.',output:'A downloadable report and evidence JSON. Production exposure remains unverified.',tab:'report'}
];
let workflowSelection='prepare',workflowContentSignature='';
$('workflow-map').innerHTML=flowSteps.map((step,i)=>`<button id="workflow-step-${step.id}" role="tab" data-explain-step="${step.id}" aria-selected="${i===0}" aria-controls="workflow-stage-content" tabindex="${i===0?0:-1}"><span>0${i+1}</span><strong>${esc(step.name)}</strong><small class="map-state">Ready to explore</small></button>`).join('');
$('process-track').innerHTML=flowSteps.map((step,i)=>`<button data-explain-step="${step.id}" class="track-step" data-track="${step.id}"><span>0${i+1}</span>${esc(step.name)}<small>Waiting</small></button>`).join('');
const countText=(number,one,many=one+'s')=>`${number} ${number===1?one:many}`;
function roleMetric(role){
  const a=current?.artifacts||{};
  if(role==='prepare')return a.repository?`${a.repository.files.length} files read at ${a.repository.commit.slice(0,8)}`:'Snapshot not available yet';
  if(role==='analyst')return a.profile?`${countText(a.profile.observations.length,'verified observation')} · ${countText(a.profile.technologies.length,'technology','technologies')}`:a.repository?`${countText(a.repository.files.length,'file')} ready for analysis`:'No repository profile yet';
  if(role==='researcher')return a.research?`${countText(a.research.sources.length,'source page')} · ${countText(a.research.incidents.length,'external record')} · ${countText((a.research.advisories||[]).length,'advisory','advisories')}`:'No research output yet';
  if(role==='reviewer')return a.review?`${countText(a.review.findings.length,'recommendation')} · ${countText(a.review.rejected_matches.length,'rejected match','rejected matches')}`:'Assessment follows retrieved evidence';
  return current?.report?'Cited Markdown and evidence JSON available':'Report follows final reference checks';
}
function renderExperience(){
  const state=current?.status,done=Boolean(current&&terminal.has(state)),a=current?.artifacts||{};
  const running=flowSteps.find(step=>current?.stages[step.id]==='running');
  const finished=flowSteps.filter(step=>current?.stages[step.id]==='completed').length;
  $('progress-title').textContent=done?(state==='completed'?'Investigation complete':state==='partial'?'Finished with limitations':state==='cancelled'?'Investigation cancelled':'Investigation stopped'):current?(running?running.name+' is working':'Investigation queued'):'Ready to investigate';
  const skipped=flowSteps.filter(step=>current?.stages[step.id]==='skipped').length;
  $('progress-description').textContent=current?(done?`${finished} completed · ${skipped} skipped · see the run outcome`:`${finished} of 5 stages completed${running?' · '+roleMetric(running.id):''}`):'Follow the code, retrieve evidence, then review the connection.';
  const labels={queued:'Waiting',running:'Working',completed:'Completed',partial:'Partial output',failed:'Failed',skipped:'Skipped',cancelled:'Cancelled'};
  flowSteps.forEach(step=>{
    const status=current?.stages[step.id]||'queued';
    const map=$('workflow-step-'+step.id);map.className='workflow-map-step '+status;map.querySelector('.map-state').textContent=current?labels[status]||status:'Click to explore';
    if(status==='running')map.setAttribute('aria-current','step');else map.removeAttribute('aria-current');
    const track=document.querySelector(`[data-track="${step.id}"]`);track.className='track-step '+status;track.querySelector('small').textContent=labels[status]||status;
  });
  document.querySelectorAll('.agent-card').forEach(card=>{
    const role=card.dataset.stage,status=current?.stages[role]||'queued';
    const output=role==='analyst'?a.profile:role==='researcher'?a.research:a.review;
    card.querySelector('.agent-status').textContent=labels[status]||status;
    card.querySelector('.agent-metric').textContent=roleMetric(role);
    const events=eventItems.filter(e=>e.stage===role),latest=events.at(-1);
    card.querySelector('.agent-operation').textContent=status==='running'?(latest?.detail||latest?.title||'Hosted request in progress. Awaiting an update.'):output?(status==='skipped'?'The saved output explains why review was skipped.':'Saved output is ready to inspect.'):status==='failed'?'This stage stopped before producing accepted output.':'Waiting for the previous stage’s evidence.';
    const button=card.querySelector('.agent-output');button.disabled=!output;button.textContent=status==='skipped'?'See why skipped →':'Inspect output →';
  });
  $('new-investigation').classList.toggle('new-ready',done);
  $('live-new').hidden=!done;$('live-new').classList.toggle('new-ready',done);$('live-report').hidden=!current?.report;$('live-report').textContent=state==='partial'?'Open report & limitations →':'Open final report →';$('view-report').classList.toggle('report-ready',Boolean(current?.report));
  $('run-outcome').hidden=!done;
  if(done){
    const report=Boolean(current.report);
    $('run-outcome').className='run-outcome '+state;
    $('run-outcome').querySelector('.outcome-mark').textContent=state==='completed'?'✓':state==='partial'?'!':state==='cancelled'?'—':'×';
    $('outcome-title').textContent=state==='completed'?'Your investigation is complete.':state==='partial'?(report?'Your report is ready—with limitations.':'Investigation ended with limitations.'):state==='cancelled'?'This investigation was cancelled.':'This investigation stopped.';
    $('outcome-label').textContent=report?'FINAL REPORT AVAILABLE':'RUN ENDED';
    $('run-outcome').querySelector('[data-new-investigation]').classList.add('new-ready');
    $('outcome-detail').textContent=state==='completed'?'Open the cited report to review findings, uncertainty, and preventive actions.':state==='partial'?'Some evidence or checks were incomplete. Review the report’s limitations before using its recommendations.':current.error||'Saved intermediate evidence remains accessible in history. You can start a new investigation.';
    $('outcome-counts').textContent=[countText(a.profile?.observations.length||0,'verified observation'),countText(a.research?.incidents.length||0,'external record'),countText(a.review?.findings.length||0,'recommendation')].join(' / ');
    $('outcome-report').hidden=!report;$('outcome-download').hidden=!report;
    $('outcome-report').textContent=state==='partial'?'Open report & limitations →':'Open final report →';
    $('outcome-download').href=`/api/jobs/${currentId}/report`;
  }
  if(!$('workflow-explainer').hidden)renderWorkflowStep();
}
function renderWorkflowStep(){
  const step=flowSteps.find(s=>s.id===workflowSelection)||flowSteps[0];
  document.querySelectorAll('#workflow-map [role="tab"]').forEach(button=>{const selected=button.dataset.explainStep===step.id;button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;});
  $('workflow-stage-content').setAttribute('aria-labelledby','workflow-step-'+step.id);
  const a=current?.artifacts||{},available=step.id==='prepare'?a.repository:step.id==='analyst'?a.profile:step.id==='researcher'?a.research:step.id==='reviewer'?a.review:current?.report;
  const proof=step.id==='analyst'?a.profile?.observations?.[0]?.quote:step.id==='researcher'?a.research?.incidents?.[0]?.source_quote:step.id==='reviewer'?a.review?.findings?.[0]?.action||a.review?.rejected_matches?.[0]?.reason:step.id==='prepare'?a.repository?.files?.[0]?.path:current?.report?'A cited Markdown report and evidence JSON are ready to inspect.':'';
  const signature=JSON.stringify([currentId,step.id,Boolean(available),roleMetric(step.id),current?.stages[step.id],proof]);
  if(signature===workflowContentSignature)return;workflowContentSignature=signature;
  $('workflow-stage-content').innerHTML=`<div class="step-explanation"><span class="eyebrow">${esc(current?.stages[step.id]||'EXPLORE THIS STEP')}</span><h3>${esc(step.title)}</h3><p>${esc(step.work)}</p></div><div class="step-evidence"><div><span>INPUT</span><p>${esc(step.input)}</p></div><div><span>OUTPUT</span><p>${esc(step.output)}</p></div><strong>${esc(roleMetric(step.id))}</strong>${proof?`<div class="workflow-proof"><span>FROM THIS RUN</span><p>${esc(proof.slice(0,450))}</p></div>`:''}<button class="button" data-output="${step.tab}" ${available?'':'disabled'}>${available?'Inspect this run’s output →':'Output appears after this stage'}</button></div>`;
}
function showWorkflow(step){
  workflowSelection=step||flowSteps.find(s=>current?.stages[s.id]==='running')?.id||'prepare';
  $('workflow-explainer').hidden=false;renderExperience();scrollToElement($('workflow-explainer'));
}
function beginNewInvestigation(){
  if(current&&!terminal.has(current.status)){document.body.classList.add('show-input');$('repo-url').focus();return;}
  eventStream?.close();clearTimeout(reloadTimer);current=null;currentId=null;eventItems=[];selectedNode=null;graphSignature='';streamConnected=false;graphView?.reset();
  const url=new URL(location.href);url.searchParams.delete('review');history.replaceState(null,'',url);
  $('repo-url').value='';$('graph-search').value='';$('control-query').value='';graphSettings.minScore=0;$('min-cvss').value=0;$('min-cvss-value').textContent='0';
  $('inspected-only').checked=false;$('show-orphans').checked=true;graphSettings.orphans=true;graphSettings.severities=['Critical','High','Medium','Low','Clean','Unscored'];document.querySelectorAll('[data-severity]').forEach(el=>{el.checked=true;});
  $('report-section').hidden=true;document.body.classList.add('show-input');renderJob();renderEvents();scrollToElement($('review-form'));$('repo-url').focus();
}
async function manageStorage(){
  try{
    const stats=await api('/api/storage');
    openDialog(`<h2>Manage local history &amp; research cache</h2><p>${stats.history.investigations} saved investigations · ${stats.history.events} activity events · ${stats.cache.files} cached files (${(stats.cache.bytes/1048576).toFixed(1)} MB).</p><p>Saved investigations contain reports, repository evidence, and event logs. The research cache contains retrieved pages, search metadata, and extracted results. There is no vector-memory database in this version. Clearing the cache means later runs may retrieve and process this evidence again.</p><p>Clearing these records cannot be undone here. API credentials and model settings are not deleted.</p>${stats.history.active?'<p class="error-banner">Finish or cancel active investigations before clearing data.</p>':''}<form id="clear-storage-form"><label for="clear-scope">Choose what to clear</label><select id="clear-scope"><option value="history">Saved investigations, reports &amp; activity</option><option value="cache">Research cache only</option><option value="all">Saved investigations + research cache</option></select><label for="clear-confirmation">Type CLEAR to confirm</label><input id="clear-confirmation" autocomplete="off" maxlength="5" placeholder="CLEAR"><button id="clear-storage-submit" class="button danger" type="submit" disabled>Clear selected local data</button><p id="storage-error" class="form-error" role="alert"></p></form>`, 'LOCAL DATA');
    $('clear-confirmation').addEventListener('input',()=>{$('clear-storage-submit').disabled=Boolean(stats.history.active)||$('clear-confirmation').value!=='CLEAR';});
    $('clear-storage-form').addEventListener('submit',async e=>{
      e.preventDefault();const scope=$('clear-scope').value;$('clear-storage-submit').disabled=true;
      try{
        const result=await api('/api/storage/clear',{method:'POST',body:JSON.stringify({scope,confirmation:$('clear-confirmation').value})});
        $('info-dialog').close();
        if(scope==='history'||scope==='all')beginNewInvestigation();await loadHistory();showToast(`Cleared ${result.cleared.history?.investigations||0} investigations and ${result.cleared.cache?.files||0} cached files.`);
      }catch(error){$('storage-error').textContent=error.message;$('clear-storage-submit').disabled=false;}
    });
  }catch(error){showToast(error.message+' Restart the local server if these controls were just installed.');}
}
$('explore-workflow').addEventListener('click',()=>showWorkflow());
$('close-workflow').addEventListener('click',()=>{$('workflow-explainer').hidden=true;scrollToElement($('progress-title'));});
$('outcome-report').addEventListener('click',()=>{switchTab('report');scrollToElement($('report-section'));});
$('manage-storage').addEventListener('click',manageStorage);
$('live-report').addEventListener('click',()=>{switchTab('report');scrollToElement($('report-section'));});
document.addEventListener('click',e=>{
  const explain=e.target.closest('[data-explain-step]');if(explain){workflowSelection=explain.dataset.explainStep;if(explain.closest('#workflow-map'))renderWorkflowStep();else showWorkflow(workflowSelection);}
  const agent=e.target.closest('[data-agent-output]');if(agent){switchTab({analyst:'overview',researcher:'incidents',reviewer:'recommendations'}[agent.dataset.agentOutput]);scrollToElement($('report-section'));}
  if(e.target.closest('[data-new-investigation]'))beginNewInvestigation();
  if(e.target.closest('[data-manage-storage]'))manageStorage();
});
$('workflow-map').addEventListener('keydown',e=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const tabs=[...$('workflow-map').querySelectorAll('[role="tab"]')],i=tabs.indexOf(document.activeElement);
  const next=tabs[e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length];workflowSelection=next.dataset.explainStep;next.focus();renderWorkflowStep();
});
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

// Original procedural sunrise, informed by the visible reference study.
const Sunrise = (() => {
  function horizonAt(x, width, height) {
    return height * (.755 + .115 * Math.pow((x - width / 2) / (width / 2), 2));
  }
  function starsFor(width, height) {
    let seed = 24681357;
    const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
    return Array.from({length:Math.min(2400, Math.round(width * height / 680))}, () => ({
      x:random() * width, y:random() * height, radius:.25 + random() * .55,
      alpha:.09 + Math.pow(random(), 3) * .34, warm:random() > .73,
    }));
  }
  function starInfluence(star, pointer, radius=75) {
    return pointer ? Math.pow(Math.max(0,1-Math.hypot(star.x-pointer.x,star.y-pointer.y)/radius),2) : 0;
  }
  function create(canvas) {
    const ctx = canvas.getContext('2d', {alpha:false});
    if (!ctx) return {focus() {}};
    const motion = matchMedia('(prefers-reduced-motion: reduce)');
    let width=0, height=0, ratio=1, texture=null, stars=[], pointer=null;
    let position=.5, target=.5, frame=0, lastTime=0, visible=true;
    function planetPath() {
      ctx.beginPath();
      ctx.moveTo(0, horizonAt(0,width,height));
      // Quadratic control point reproduces horizonAt exactly.
      ctx.quadraticCurveTo(width/2, height*.64, width, horizonAt(width,width,height));
      ctx.lineTo(width,height);ctx.lineTo(0,height);ctx.closePath();
    }
    function rimPath() {
      ctx.beginPath();ctx.moveTo(0,horizonAt(0,width,height));
      ctx.quadraticCurveTo(width/2,height*.64,width,horizonAt(width,width,height));
    }
    function glow(x,y,rx,ry,stops) {
      ctx.save();ctx.translate(x,y);ctx.scale(rx,ry);
      const gradient=ctx.createRadialGradient(0,0,0,0,0,1);
      stops.forEach(([offset,color])=>gradient.addColorStop(offset,color));
      ctx.fillStyle=gradient;ctx.fillRect(-1,-1,2,2);ctx.restore();
    }
    function prepare() {
      const bounds=canvas.getBoundingClientRect();
      const nextRatio=Math.min(devicePixelRatio||1,2);
      if (!bounds.width || !bounds.height) return false;
      if (width===bounds.width && height===bounds.height && ratio===nextRatio) return true;
      width=bounds.width;height=bounds.height;ratio=nextRatio;
      canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
      texture=document.createElement('canvas');texture.width=canvas.width;texture.height=canvas.height;
      const sky=texture.getContext('2d');
      sky.setTransform(canvas.width/width,0,0,canvas.height/height,0,0);
      sky.fillStyle='#08090c';sky.fillRect(0,0,width,height);
      const blue=sky.createLinearGradient(0,height*.2,0,height);
      blue.addColorStop(0,'#08090c00');blue.addColorStop(.65,'#0b183c66');blue.addColorStop(1,'#17234e99');
      sky.fillStyle=blue;sky.fillRect(0,0,width,height);
      stars=starsFor(width,height);
      sky.shadowBlur=3;
      stars.forEach(star=>{
        sky.shadowColor=star.warm?'#d4b291':'#9cbdf5';
        sky.fillStyle=star.warm?`rgba(203,163,132,${star.alpha})`:`rgba(148,182,220,${star.alpha})`;
        sky.beginPath();sky.arc(star.x,star.y,star.radius,0,Math.PI*2);sky.fill();
      });
      return true;
    }
    function draw() {
      if (!prepare()) return;
      ctx.setTransform(canvas.width/width,0,0,canvas.height/height,0,0);
      ctx.drawImage(texture,0,0,width,height);
      // Only nearby stars brighten; keep the surrounding sky and text untouched.
      if(pointer){
        ctx.save();ctx.globalCompositeOperation='screen';ctx.shadowBlur=8;
        stars.forEach(star=>{
          const influence=starInfluence(star,pointer);
          if(influence<.015 || star.y>=horizonAt(star.x,width,height))return;
          ctx.shadowColor=star.warm?'#ffd2a8':'#b4ccff';
          ctx.fillStyle=`rgba(218,231,255,${influence*.85})`;
          ctx.beginPath();ctx.arc(star.x,star.y,star.radius+influence*.8,0,Math.PI*2);ctx.fill();
        });ctx.restore();
      }
      const sunX=width*position, sunY=horizonAt(sunX,width,height);
      const scale=height;
      // Wide cool air hugs the whole planet, even opposite the warm sunrise.
      ctx.save();ctx.globalCompositeOperation='screen';
      rimPath();ctx.strokeStyle='#6353a066';ctx.lineWidth=20;ctx.filter='blur(14px)';ctx.stroke();
      ctx.filter='none';
      glow(sunX,sunY,width*.58,scale*.62,[[0,'#6b284a62'],[.35,'#45204a44'],[.75,'#231c4022'],[1,'#151b3400']]);
      glow(sunX,sunY,width*.33,scale*.30,[[0,'#ffb49a9c'],[.12,'#e282737b'],[.37,'#a4537052'],[.7,'#60346b27'],[1,'#472a6800']]);
      glow(sunX,sunY,width*.20,scale*.13,[[0,'#ffe7d7dd'],[.13,'#ffbfa3b0'],[.36,'#ef948079'],[.7,'#b45d6b29'],[1,'#8c426700']]);
      ctx.restore();
      // Occlude the lower half of the sun: it is dawn behind a real silhouette.
      planetPath();ctx.fillStyle='#08090b';ctx.fill();
      ctx.save();planetPath();ctx.clip();ctx.globalCompositeOperation='screen';
      glow(sunX,sunY,width*.27,scale*.27,[[0,'#b8733738'],[.3,'#81502420'],[1,'#29190a00']]);
      ctx.restore();
      // The illuminated rim changes from cool violet to coral to white near dawn.
      const rim=ctx.createLinearGradient(sunX-width*.65,0,sunX+width*.65,0);
      [[0,'#36366544'],[.22,'#60508a99'],[.36,'#c58294cc'],[.44,'#ffbfa5'],[.5,'#fff5e9'],[.56,'#ffbfa5'],[.64,'#c58294cc'],[.78,'#60508a99'],[1,'#36366544']].forEach(([p,c])=>rim.addColorStop(p,c));
      ctx.save();rimPath();ctx.strokeStyle=rim;ctx.lineWidth=1.25;ctx.shadowBlur=6;ctx.shadowColor='#ffbdac';ctx.stroke();ctx.restore();
      // Small flattened solar crest, attached to the curve rather than floating.
      ctx.save();ctx.globalCompositeOperation='screen';
      glow(sunX,sunY-1,width*.055,scale*.023,[[0,'#fff9eedd'],[.14,'#ffe9d8aa'],[.4,'#ffc2a75a'],[1,'#f09a8300']]);
      ctx.restore();
      // A gentle lower fade blends the planet into the existing black workbench.
      const fade=ctx.createLinearGradient(0,height*.88,0,height);
      fade.addColorStop(0,'#09090900');fade.addColorStop(1,'#090909');ctx.fillStyle=fade;ctx.fillRect(0,height*.88,width,height*.12);
    }
    function tick(time) {
      frame=0;
      if (!visible || document.hidden) {lastTime=0;return;}
      const delta=lastTime?Math.min(time-lastTime,64):16;lastTime=time;
      position=motion.matches?target:position+(target-position)*(1-Math.exp(-delta/165));
      if (Math.abs(target-position)<.0001)position=target;
      draw();
      if (position!==target)frame=requestAnimationFrame(tick);else lastTime=0;
    }
    function schedule() {if (!frame && visible && !document.hidden)frame=requestAnimationFrame(tick);}
    function focus(value) {target=Math.max(.08,Math.min(.92,value));schedule();}
    const observer=new ResizeObserver(schedule);observer.observe(canvas);
    const visibility=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible)schedule();});visibility.observe(canvas);
    document.addEventListener('visibilitychange',()=>{if(document.hidden)pointer=null;schedule();});
    motion.addEventListener('change',()=>{if(motion.matches)position=target;schedule();});
    function hover(point) {pointer=point;schedule();}
    canvas.parentElement?.addEventListener('pointermove',event=>{
      if(event.pointerType==='touch')return;
      const box=canvas.getBoundingClientRect();hover({x:event.clientX-box.left,y:event.clientY-box.top});
    },{passive:true});
    canvas.parentElement?.addEventListener('pointerleave',()=>hover(null));
    window.addEventListener('blur',()=>hover(null));
    document.addEventListener('scroll',()=>{if(pointer)hover(null);},{passive:true,capture:true});
    schedule();
    return {focus,hover};
  }
  return {create,horizonAt,starsFor,starInfluence};
})();

// Landing-only role emphasis; investigation stages remain controlled by the runner.
(() => {
  const intro = document.querySelector('.landing-intro');
  const roles = [...document.querySelectorAll('[data-intro-role]')];
  if (!intro || !roles.length) return;
  const scene = Sunrise.create(intro.querySelector('.sunrise-scene'));
  function activate(role) {
    roles.forEach(item => item.setAttribute('aria-pressed', String(item === role)));
    const region = intro.querySelector('.sunrise-scene').getBoundingClientRect();
    const bounds = role.getBoundingClientRect();
    scene.focus((bounds.left + bounds.width / 2 - region.left) / region.width);
  }
  roles.forEach(role => {
    role.addEventListener('pointerenter', event => { if (event.pointerType !== 'touch') activate(role); });
    role.addEventListener('focus', () => activate(role));
    role.addEventListener('click', () => activate(role));
  });
  window.addEventListener('resize', () => activate(roles.find(role => role.getAttribute('aria-pressed') === 'true')));
})();

// Pointer light for real text: no duplicate text layers or layout changes.
const LuminousType = (() => {
  function isIntroText(element) {return Boolean(element?.closest('.landing-intro'));}
  function follow(state, delta, reduced) {
    const blend=reduced?1:1-Math.exp(-Math.min(delta,64)/65);
    state.x+=(state.targetX-state.x)*blend;state.y+=(state.targetY-state.y)*blend;
    state.strength+=(state.targetStrength-state.strength)*blend;
    if(Math.abs(state.targetStrength-state.strength)<.005)state.strength=state.targetStrength;
    return Math.abs(state.targetX-state.x)>.1||Math.abs(state.targetY-state.y)>.1||state.strength!==state.targetStrength;
  }
  function mount(root=document) {
    if(!CSS.supports('background-clip','text')||!CSS.supports('color','color-mix(in srgb,white,black)'))return;
    const motion=matchMedia('(prefers-reduced-motion: reduce)');
    const selector='h2,p,.intro-role>span,.intro-role>strong,.intro-assurance,.eyebrow';
    const states=new Map();let active=null,frame=0,lastTime=0;
    function remove(element){
      element.classList.remove('luminous-text');
      ['--type-base','--type-x','--type-y','--type-strength'].forEach(key=>element.style.removeProperty(key));
      states.delete(element);
    }
    function tick(time){
      frame=0;const delta=lastTime?time-lastTime:16;lastTime=time;let moving=false;
      states.forEach((state,element)=>{
        if(!element.isConnected){remove(element);return;}
        moving=follow(state,delta,motion.matches)||moving;
        if(!state.targetStrength&&!state.strength){remove(element);return;}
        element.style.setProperty('--type-x',`${state.x}px`);
        element.style.setProperty('--type-y',`${state.y}px`);
        element.style.setProperty('--type-strength',`${(state.strength*100).toFixed(2)}%`);
      });
      if(moving)schedule();else lastTime=0;
    }
    function schedule(){if(!frame&&!document.hidden)frame=requestAnimationFrame(tick);}
    function light(element,x,y){
      const previous=states.get(active);if(previous&&active!==element)previous.targetStrength=0;
      active=element;
      if(!element){schedule();return;}
      let state=states.get(element);
      if(!state){
        const base=getComputedStyle(element).color;
        state={x,y,targetX:x,targetY:y,strength:0,targetStrength:1};states.set(element,state);
        element.style.setProperty('--type-base',base);element.classList.add('luminous-text');
      }
      state.targetX=x;state.targetY=y;state.targetStrength=1;schedule();
    }
    root.addEventListener('pointermove',event=>{
      if(event.pointerType==='touch')return;
      let element=event.target.closest(selector);
      // Do not make inherited SVG icons or interactive descendants transparent.
      if(!isIntroText(element)||element.querySelector('svg,input,select,button,a'))element=null;
      if(!element){light(null);return;}
      const bounds=element.getBoundingClientRect();light(element,event.clientX-bounds.left,event.clientY-bounds.top);
    },{passive:true});
    root.addEventListener('focusin',event=>{
      const element=event.target.closest('.intro-role')?.querySelector('strong');
      if(isIntroText(element)){const box=element.getBoundingClientRect();light(element,box.width/2,box.height/2);}
    });
    root.addEventListener('focusout',()=>light(null));
    root.addEventListener('scroll',()=>light(null),{passive:true,capture:true});
    root.documentElement.addEventListener('pointerleave',()=>light(null));
    window.addEventListener('blur',()=>light(null));
    root.addEventListener('visibilitychange',()=>{
      if(document.hidden){states.forEach((_,element)=>remove(element));active=null;}else schedule();
    });
    motion.addEventListener('change',schedule);
  }
  return {follow,mount,isIntroText};
})();
LuminousType.mount();

// Paint only existing rectangular borders near the pointer. The overlay never
// receives input or changes panel layout, graph drawing, or graph gestures.
(() => {
  const finePointer = matchMedia('(any-hover: hover) and (any-pointer: fine)');
  const canvas = document.createElement('canvas');
  canvas.className = 'edge-light';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.append(canvas);
  const context = canvas.getContext('2d');
  if (!context) { canvas.remove(); return; }
  const surfaces = '.site-header,.brand,.nav-link,.workspace-settings,.input-card,.input-card input,.input-card select,.button,.run-outcome,.run-progress,.workflow,.agent-card,.graph-panel,.activity-panel,.inspector-panel,.review-tray,.report-section,.recent-item,.graph-search input,.graph-tabs button,.panel-bar,.controls-body,dialog[open]';
  let pointer = null, frame = 0;
  function resize() { schedule(); }
  function paint() {
    frame = 0;
    // CSS percentages exclude the scrollbar, while innerWidth includes it.
    // Map viewport coordinates to the actual canvas box, including fractional
    // dimensions and DPR changes after browser zoom or moving between screens.
    const box = canvas.getBoundingClientRect();
    if (!box.width || !box.height) return;
    const ratio = Math.min(devicePixelRatio || 1, 2);
    const width = Math.round(box.width * ratio), height = Math.round(box.height * ratio);
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
    const scaleX = canvas.width / box.width, scaleY = canvas.height / box.height;
    context.setTransform(scaleX, 0, 0, scaleY, -box.left * scaleX, -box.top * scaleY);
    if (!pointer || !finePointer.matches || document.hidden) return;
    const {x, y} = pointer, radius = 135;
    const light = context.createRadialGradient(x, y, 0, x, y, radius);
    light.addColorStop(0, '#fff3d9');
    light.addColorStop(.15, '#efb9a9e6');
    light.addColorStop(.35, '#8edbe1ba');
    light.addColorStop(.60, '#a383e66b');
    light.addColorStop(1, '#a383e600');
    context.strokeStyle = light;
    context.lineWidth = 1.2;
    context.shadowColor = '#b8a5e9';
    context.shadowBlur = 7;
    // Query at draw time so dynamic report panels and dialogs need no observers.
    document.querySelectorAll(surfaces).forEach(element => {
      const bounds = element.getBoundingClientRect();
      if (!bounds.width || !bounds.height || bounds.bottom < 0 || bounds.top > innerHeight) return;
      const dx = Math.max(bounds.left - x, 0, x - bounds.right);
      const dy = Math.max(bounds.top - y, 0, y - bounds.bottom);
      if (Math.hypot(dx, dy) > radius) return;
      const edge = Math.min(Math.abs(x - bounds.left), Math.abs(x - bounds.right), Math.abs(y - bounds.top), Math.abs(y - bounds.bottom));
      if (!dx && !dy && edge > radius) return;
      const style = getComputedStyle(element);
      if (style.visibility === 'hidden' || style.display === 'none') return;
      // Use actual border widths: never invent boxes around borderless controls.
      const top = parseFloat(style.borderTopWidth) || 0;
      const right = parseFloat(style.borderRightWidth) || 0;
      const bottom = parseFloat(style.borderBottomWidth) || 0;
      const left = parseFloat(style.borderLeftWidth) || 0;
      const x1 = bounds.left + left / 2, x2 = bounds.right - right / 2;
      const y1 = bounds.top + top / 2, y2 = bounds.bottom - bottom / 2;
      const edges = [
        [top, x1, y1, x2, y1],
        [right, x2, y1, x2, y2],
        [bottom, x2, y2, x1, y2],
        [left, x1, y2, x1, y1],
      ];
      context.beginPath();
      edges.forEach(([width, startX, startY, endX, endY]) => {
        if (width > 0) { context.moveTo(startX, startY); context.lineTo(endX, endY); }
      });
      context.stroke();
    });
  }
  function schedule() { if (!frame) frame = requestAnimationFrame(paint); }
  document.addEventListener('pointermove', event => {
    pointer = event.pointerType === 'touch' ? null : {x:event.clientX, y:event.clientY};
    schedule();
  }, {passive:true});
  function clear() { pointer = null; schedule(); }
  document.documentElement.addEventListener('pointerleave', clear);
  window.addEventListener('blur', clear);
  document.addEventListener('visibilitychange', clear);
  document.addEventListener('scroll', schedule, {passive:true, capture:true});
  finePointer.addEventListener('change', clear);
  window.addEventListener('resize', resize);
  resize();
})();
