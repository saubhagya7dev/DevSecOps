import re
from datetime import date, timedelta
from .reporting import render_report  # Backwards-compatible public import.


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
        assessments = finding.get('prerequisite_assessments', [])
        contradicted = [a for a in assessments if a['state'] == 'contradicted'
                        and a['evidence_ids'] and a['incident_ids']
                        and all(x in finding['evidence_ids'] for x in a['evidence_ids'])
                        and all(x in finding['incident_ids'] for x in a['incident_ids'])]
        if contradicted:
            reason = 'Material prerequisite contradicted: ' + '; '.join(a['reason'] for a in contradicted)
            review['rejected_matches'].extend({'incident_id': x, 'reason': reason} for x in finding['incident_ids'])
            warnings.append(f"Rejected recommendation {finding['id']}: contradicted prerequisite.")
            continue
        unresolved = [a for a in assessments if a['state'] != 'supported'
                      or not a['evidence_ids'] or not a['incident_ids']
                      or not all(x in finding['evidence_ids'] and observations[x]['kind'] == 'observed' for x in a['evidence_ids'])
                      or not all(x in finding['incident_ids'] for x in a['incident_ids'])]
        if finding['classification'] == 'Supported concern' and (not assessments or unresolved or finding['missing_information']):
            finding['classification'] = 'Needs verification'
            finding['missing_information'].extend(a['prerequisite'] for a in unresolved
                                                   if a['prerequisite'] not in finding['missing_information'])
            if not assessments:
                finding['missing_information'].append('No structured prerequisite assessment was supplied.')
            warnings.append(f"Downgraded {finding['id']}: material prerequisites remain unverified.")
        valid.append(finding)
    review['findings'] = valid
    review['existing_defenses'] = [d for d in review['existing_defenses'] if d['evidence_ids'] and all(x in observations for x in d['evidence_ids'])]
    review['rejected_matches'] = [r for r in review['rejected_matches'] if r['incident_id'] in incidents]
    return review, warnings
