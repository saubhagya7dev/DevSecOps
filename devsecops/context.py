"""Small evidence views for hosted models; full fetched evidence stays in saved artifacts."""
import json
import re


def short(value, limit):
    return value if len(value) <= limit else value[:limit] + ' [excerpt]'


def research_profile(profile):
    return {'technologies': [{'name': short(t['name'], 80), 'version': short(t['version'], 60)}
                             for t in profile['technologies'][:8]],
            'research_questions': [short(q, 240) for q in profile['research_questions'][:4]],
            'observations': [{'id': o['id'], 'claim': short(o['claim'], 160), 'kind': o['kind']}
                             for o in profile['observations'][:12]],
            'coverage_limit': 'Bounded profile view. Repository behavior and deployment exposure may be unknown.'}


def source_views(sources, profile, budget=6000):
    """Rank contiguous windows, including page introduction/date context. Quotes stay verifiable."""
    terms = set(re.findall(r'[a-z][a-z0-9_-]{3,}', json.dumps(research_profile(profile)).lower()))
    terms -= {'observations', 'research_questions', 'kind', 'claim', 'technologies', 'version', 'observed'}
    per_source = max(200, budget // max(1, len(sources)))
    views = []
    for source in sources:
        text = source['text']
        width = min(650, per_source // 2)
        intro = min(350, per_source // 3)
        windows = [(i, text[i:i + width]) for i in range(intro, len(text), max(1, width))]
        scored = sorted(windows, key=lambda item: (
            sum(term in item[1].lower() for term in terms) +
            2 * sum(term in item[1].lower() for term in ('exploit', 'attacker', 'vulnerability', 'incident', 'mitigat'))), reverse=True)
        selected = {0: text[:intro]}
        remaining = per_source - len(selected[0])
        for offset, passage in scored:
            if offset == 0 or remaining < 100:
                continue
            selected[offset] = passage[:remaining]
            remaining -= len(selected[offset])
        views.append({'id': source['id'], 'title': short(source['title'], 120), 'url': source['url'],
                      'passages': [text] if len(text) <= per_source else [passage for _, passage in sorted(selected.items())],
                      'coverage': 'Selected contiguous excerpts; omitted text has not been reviewed by this role.'})
    return views


def reviewer_views(profile, research):
    # Full page text is never needed here: accepted incidents already carry checked passages.
    observations = [{key: short(o[key], 140 if key == 'quote' else 100)
                     if isinstance(o[key], str) else o[key]
                     for key in ('id', 'claim', 'quote', 'kind', 'path', 'start_line', 'end_line')}
                    for o in profile['observations'][:16]]
    incidents = []
    for incident in research['incidents'][:4]:
        incidents.append({key: [short(item, 120) for item in value[:3]] if isinstance(value, list)
                          else short(value, 320) if isinstance(value, str) else value
                          for key, value in incident.items()})
    return ({'observations': observations,
             'technologies': [{'name': short(t['name'], 80), 'version': short(t['version'], 60),
                               'evidence_ids': t['evidence_ids'][:4]} for t in profile['technologies'][:8]],
             'unknowns': [short(q, 160) for q in profile['unknowns'][:3]],
             'coverage_limit': 'At most sixteen observations and four incidents, with shortened fields. Missing detail remains unknown.'},
            {'incidents': incidents, 'research_limitations': [short(q, 180) for q in research['research_limitations'][:3]]})
