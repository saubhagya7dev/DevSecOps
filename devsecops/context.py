"""Small evidence views for hosted models; full fetched evidence stays in saved artifacts."""
import json
import re
import copy
import math


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


def ranked_source_views(sources, profile, budget=6000):
    """Spend the unchanged shared budget on distinct mechanism/prerequisite passages."""
    terms = set(re.findall(r'[a-z][a-z0-9_-]{3,}', json.dumps(research_profile(profile)).lower()))
    terms -= {'observations', 'research_questions', 'kind', 'claim', 'technologies', 'version', 'observed', 'unknown'}
    pool = []
    for source in sources:
        text = source['text']
        for start in range(0, len(text), 600):
            passage = text[start:start + 1000]
            lower = passage.lower()
            score = sum(term in lower for term in terms)
            score += 3 * sum(term in lower for term in ('attacker', 'exploited', 'compromis', 'prerequisite', 'requires', 'authenticated'))
            score += 2 * len(re.findall(r'cve-\d{4}-\d+|t\d{4}(?:\.\d{3})?', lower))
            pool.append((score, source['id'], start, passage, source))
    selected, seen_text, counts, spans = {}, set(), {}, {}
    remaining = min(6000, budget)
    for score, sid, start, passage, source in sorted(pool, key=lambda row: (-row[0], row[1], row[2])):
        normalized = ' '.join(passage.lower().split())
        if (remaining < 100 or normalized in seen_text or counts.get(sid, 0) >= 2
                or (sid not in selected and len(selected) >= 3)
                or any(start < end and start + len(passage) > begin for begin, end in spans.get(sid, []))):
            continue
        chosen = passage[:remaining]
        seen_text.add(normalized)
        counts[sid] = counts.get(sid, 0) + 1
        spans.setdefault(sid, []).append((start, start + len(chosen)))
        view = selected.setdefault(sid, {'id': sid, 'title': short(source['title'], 100), 'passages': []})
        view['passages'].append(chosen)
        remaining -= len(chosen)
    return list(selected.values())


def estimate_tokens(payload):
    # Deliberately conservative byte estimate, including system prompt and JSON schema.
    # It is not a provider tokenizer or proof of available account quota.
    return math.ceil(len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) / 2)


def smaller_context(data):
    """Rebuild a smaller view without changing IDs, instructions, schema, or stored evidence."""
    reduced = copy.deepcopy(data)
    if reduced.get('technique_candidates'):
        reduced['technique_candidates'] = []
        return reduced
    sources = reduced.get('sources', [])
    if sources:
        if len(sources) > 1:
            reduced['sources'] = sources[:-1]
        else:
            passages = sources[0].get('passages', [])
            if len(passages) > 1:
                sources[0]['passages'] = passages[:1]
            elif passages and len(passages[0]) > 150:
                sources[0]['passages'] = [passages[0][:max(150, len(passages[0]) // 2)]]
            else:
                return None
        return reduced
    if 'profile' in reduced:
        profile = reduced['profile']
        for field in ('observations', 'research_questions', 'technologies', 'unknowns'):
            if isinstance(profile.get(field), list) and len(profile[field]) > 1:
                profile[field] = profile[field][:max(1, len(profile[field]) // 2)]
                return reduced
    return None


def reviewer_views(profile, research):
    # Full page text is never needed here: accepted incidents already carry checked passages.
    observations = [{key: short(o[key], 140 if key == 'quote' else 100)
                     if isinstance(o[key], str) else o[key]
                     for key in ('id', 'claim', 'quote', 'kind', 'path', 'start_line', 'end_line')}
                    for o in profile['observations'][:16]]
    incidents = []
    for incident in research['incidents'][:4]:
        incidents.append({key: [short(item, 120) for item in value[:3]] if isinstance(value, list)
                          else short(value, 800 if key == 'source_quote' else 320) if isinstance(value, str) else value
                          for key, value in incident.items()})
    return ({'observations': observations,
             'technologies': [{'name': short(t['name'], 80), 'version': short(t['version'], 60),
                               'evidence_ids': t['evidence_ids'][:4]} for t in profile['technologies'][:8]],
             'unknowns': [short(q, 160) for q in profile['unknowns'][:3]],
             'coverage_limit': 'At most sixteen observations and four incidents, with shortened fields. Missing detail remains unknown.'},
            {'incidents': incidents, 'research_limitations': [short(q, 180) for q in research['research_limitations'][:3]]})
