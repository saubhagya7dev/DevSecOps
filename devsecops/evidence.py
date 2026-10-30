import re
from datetime import date, timedelta
from urllib.parse import quote, urlsplit


def normalized(text):
    return ' '.join(text.split())


def validate_profile(profile, repo):
    files = {f['path']: f for f in repo['files']}
    accepted, rejected, ids = [], [], set()
    for obs in profile['observations']:
        file = files.get(obs['path'])
        start, end = obs['start_line'], obs['end_line']
        lines = file['content'].splitlines() if file else []
        excerpt = '\n'.join(lines[start - 1:end]) if 1 <= start <= end <= len(lines) else ''
        if (not re.fullmatch(r'E[1-9][0-9]*', obs['id']) or obs['id'] in ids or not excerpt
                or normalized(obs['quote']) != normalized(excerpt) or '[REDACTED:' in excerpt):
            rejected.append(f"Rejected repository observation {obs['id']}: invalid or mismatched citation.")
            continue
        ids.add(obs['id'])
        accepted.append({**obs, 'url': f"{file['url']}#L{start}-L{end}"})
    profile['observations'] = accepted
    if not accepted:
        profile['summary'] = 'No repository observations passed the citation checks. Inspect the saved coverage and validation limitations before drawing conclusions.'
        profile['research_questions'] = []
    for key in ('technologies', 'components'):
        profile[key] = [item for item in profile[key] if item['evidence_ids'] and all(x in ids for x in item['evidence_ids'])]
    profile['unknowns'].extend(rejected)
    return profile, rejected


def validate_research(research, days, today=None):
    today = today or date.today()
    since = today - timedelta(days=days)
    sources = {s['id']: s for s in research['sources']}
    accepted, warnings, ids = [], [], set()
    for incident in research['incidents']:
        source = sources.get(incident['source_id'])
        quote = normalized(incident['source_quote'])
        if (incident['id'] in ids or not re.fullmatch(r'I[1-9][0-9]*', incident['id']) or not source
                or not 40 <= len(quote) <= 800 or quote not in normalized(source['text'])):
            warnings.append(f"Rejected incident {incident['id']}: source passage could not be verified.")
            continue
        ids.add(incident['id'])
        try:
            published = date.fromisoformat(incident['publication_date'])
            incident['recency'] = 'Recent report' if since <= published <= today else 'Background / outside window'
            if published > today:
                incident['publication_date'] = 'unknown'
                incident['recency'] = 'Publication date unverified'
        except ValueError:
            incident['publication_date'] = 'unknown'
            incident['recency'] = 'Publication date unverified'
        try:
            if date.fromisoformat(incident['incident_date']) > today:
                incident['incident_date'] = 'unknown'
        except ValueError:
            incident['incident_date'] = 'unknown'
        accepted.append(incident)
        if incident.get('supporting_sources'):
            valid_support = []
            for support in incident['supporting_sources']:
                other = sources.get(support.get('source_id'))
                passage = normalized(support.get('source_quote', ''))
                if other and 40 <= len(passage) <= 800 and passage in normalized(other['text']):
                    valid_support.append(support)
                else:
                    warnings.append(f'Rejected secondary source support for {incident["id"]}.')
            incident['supporting_sources'] = valid_support
    research['incidents'] = accepted
    research['research_limitations'].extend(warnings)
    return research, warnings


def validate_review(review, profile, research):
    observations = {o['id']: o for o in profile['observations']}
    incidents = {i['id']: i for i in research['incidents']}
    valid, warnings, ids = [], [], set()
    for finding in review['findings']:
        if (finding['id'] in ids or not finding['evidence_ids'] or not finding['incident_ids']
                or not all(x in observations for x in finding['evidence_ids'])
                or not all(x in incidents for x in finding['incident_ids'])
                or not finding['action'].strip() or not finding['verification'].strip()):
            warnings.append(f"Rejected recommendation {finding['id']}: incomplete evidence chain.")
            continue
        ids.add(finding['id'])
        if finding['classification'] == 'Supported concern' and all(observations[x]['kind'] != 'observed' for x in finding['evidence_ids']):
            finding['classification'] = 'Needs verification'
            finding['missing_information'].append('Repository evidence is inferred; confirm the prerequisite.')
            warnings.append(f"Downgraded {finding['id']}: inferred evidence cannot establish the prerequisite.")
        if finding['classification'] == 'Supported concern' and all(
                incidents[x]['source_type'] == 'background guidance' for x in finding['incident_ids']):
            finding['classification'] = 'Background lesson'
            warnings.append(f'Downgraded {finding["id"]}: background mechanisms alone cannot establish a concern.')
        valid.append(finding)
    review['findings'] = valid
    review['existing_defenses'] = [d for d in review['existing_defenses'] if d['evidence_ids'] and all(x in observations for x in d['evidence_ids'])]
    review['rejected_matches'] = [r for r in review['rejected_matches'] if r['incident_id'] in incidents]
    return review, warnings


def md_text(value):
    # Render model text as prose, not executable HTML or model-supplied Markdown links.
    value = str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return re.sub(r'([\\`*_{}\[\]()#+!|])', r'\\\1', value)


def md_url(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            return '#'
    except ValueError:
        return '#'
    return quote(value, safe=':/?#@!$&=+%,;~-')


def render_report(repo, profile, research, review, validation, demo=False):
    t = md_text
    lines = ['# Repository threat review', '', f"Repository: {repo['url']}",
             f"Commit: `{repo['commit']}`", '',
             '**ILLUSTRATIVE OFFLINE EXAMPLE — not a real repository assessment or incident investigation.**' if demo else '**Static, read-only review. Production exposure and exploitability are not established.**', '',
             '## Repository overview', '', t(profile['summary']), '',
             '### Technologies', '']
    for tech in profile['technologies']:
        lines.append(f"- {t(tech['name'])}: {t(tech['version'])} ({', '.join(tech['evidence_ids'])})")
    lines += ['', '### Components', '']
    for component in profile['components']:
        lines.append(f"- {t(component['name'])}: {t(component['description'])} ({', '.join(component['evidence_ids'])})")
    coverage = repo['coverage']
    lines += ['', '## Analysis coverage', '',
              f"- Files inspected: {coverage['files_read']} of {coverage['files_in_tree']} files in the returned tree.",
              f"- Files truncated: {coverage['truncated_files']}.",
              f"- Eligible files skipped by budget or error: {coverage['files_skipped_by_budget_or_error']}.",
              f"- GitHub tree incomplete: {'yes' if coverage['tree_truncated'] else 'no'}.", '',
              'Only a bounded selection of files was inspected. Uninspected or redacted content may contain relevant controls or risks.', '',
              '## Review', '', t(review['summary']), '', '## Recommendations', '']
    if not review['findings']:
        lines += ['No evidence-backed recommendations were established. This is not a declaration that the repository is secure.', '']
    for f in review['findings']:
        lines += [f"### {t(f['title'])}", '', f"**{f['classification']} · Impact: {f['impact']} · Confidence: {f['confidence']}**", '',
                  f"Mechanism: {t(f['mechanism'])}", '', f"Prerequisite: {t(f['prerequisite'])}", '',
                  t(f['reasoning']), '', f"Counterevidence: {t(f['counterevidence'])}", '',
                  f"Evidence: {', '.join(f['evidence_ids'])}. Incidents: {', '.join(f['incident_ids'])}.", '',
                  f"**Action:** {t(f['action'])}", '', f"**Verify:** {t(f['verification'])}", '',
                  '**Missing information:** ' + t('; '.join(f['missing_information']) or 'None identified within inspected evidence.'), '']
    lines += ['## Existing defenses', '']
    lines += [f"- {t(d['description'])} ({', '.join(d['evidence_ids'])})" for d in review['existing_defenses']] or ['None established from the inspected evidence.']
    lines += ['', '## Repository evidence', '']
    for o in profile['observations']:
        lines += [f"### {o['id']}: {t(o['claim'])}", '',
                  f"[{t(o['path'])}, lines {o['start_line']}–{o['end_line']}]({md_url(o['url'])}) · {o['kind']}", '',
                  '> ' + t(o['quote']).replace('\n', '\n> '), '']
    lines += ['## Documented external evidence and sources', '']
    sources = {s['id']: s for s in research['sources']}
    for i in research['incidents']:
        s = sources[i['source_id']]
        lines += [f"### {i['id']}: {t(i['title'])}", '', f"[{t(s['title'])}]({md_url(s['url'])})", '',
                  f"Type: {i['source_type']}. Published: {i['publication_date']}. Incident date: {i['incident_date']}. {i['recency']}.", '',
                  f"Victim: {t(i['victim'])}. Retrieved: {t(s['retrieved_at'])}.", '',
                  t(i['mechanism']), '', 'Prerequisites: ' + t('; '.join(i['prerequisites'])), '',
                  '> ' + t(i['source_quote']), '']
        for support in i.get('supporting_sources', []):
            if support['source_id'] != i['source_id']:
                other = sources[support['source_id']]
                lines += [f'Additional source: [{t(other["title"])}]({md_url(other["url"])})', '',
                          'Publication: ' + t(support.get('publication_date', 'unknown')) + '. Retrieval: ' + t(other['retrieved_at']), '',
                          '> ' + t(support['source_quote']), '']
    if research.get('coverage'):
        lines += ['## Discovery coverage', '', t(research.get('outcome', '')), '',
                  *[f'- {t(key)}: {t(value)}' for key, value in research['coverage'].items()], '']
    if research.get('advisories'):
        lines += ['## Package vulnerability advisories — not proof of an incident', '']
        for advisory in research['advisories']:
            package = advisory['package']
            lines += [f'### {t(advisory["id"])}: {t(advisory["title"])}', '',
                      f'Package: {t(package["ecosystem"])} / {t(package["name"])}. {t(advisory["version_assessment"])}', '',
                      'Identifiers: ' + t(', '.join(advisory['identifiers'])), '',
                      'Provider-reported fixes: ' + t(', '.join(advisory['fixed_versions']) or 'unknown'), '',
                      'Published: ' + t(advisory['publication_date']) + '. Retrieved: ' + t(advisory['retrieved_at']), '']
            lines += [f'- [{t(origin["provider"])} record]({md_url(origin["url"])})' for origin in advisory['provenance']]
    if research.get('techniques'):
        lines += ['', '## ATT&CK candidates — background mechanisms', '']
        lines += [f'- [{t(item["id"])}: {t(item["name"])}]({md_url(item["url"])})' for item in research['techniques']]
        lines += ['', 'Candidate techniques are not confirmed mappings, incidents, or proof of target exposure.', '']
        lines += [f'- {t(item["incident_id"])}: {t(item["status"])} — {t(", ".join(item["technique_ids"]))}'
                  for item in research.get('attack_mappings', [])]
    if research.get('historical_records'):
        lines += ['', '## Historical VCDB records — limited technical detail', '']
        for item in research['historical_records']:
            lines += [f'- {t(item["id"])}: {t(item["summary"])}. {t(item["limitation"])}',
                      f'  Incident date: {t(item["incident_date"])}; year: {t(item["incident_year"])}. Publication: unknown. Retrieved: {t(item["retrieved_at"])}.',
                      f'  [Official record]({md_url(item["provenance"])})']
    lines += ['', '## Rejected matches', '']
    lines += [f"- {r['incident_id']}: {t(r['reason'])}" for r in review['rejected_matches']] or ['None recorded.']
    lines += ['', '## Unknowns and limitations', '']
    for item in profile['unknowns'] + research['research_limitations'] + review['questions'] + validation:
        lines.append('- ' + t(item))
    lines += ['', 'Citation checks establish passage/reference integrity, not independent proof of semantic correctness. Recommendations remain AI-generated and require review.', '']
    return '\n'.join(lines)
