"""Safe Markdown presentation of accepted review evidence."""
import re
from urllib.parse import quote, urlsplit


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
        for assessment in f.get('prerequisite_assessments', []):
            lines += [f"- Prerequisite ({t(assessment['state'])}): {t(assessment['prerequisite'])} — {t(assessment['reason'])}", '']
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
