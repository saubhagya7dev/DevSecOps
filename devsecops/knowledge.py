"""Official ATT&CK STIX normalization and optional VCDB history, entirely in Python."""
import base64
import json
import os
import re
from datetime import datetime, timezone, date
from urllib.parse import urlencode

from .network import FetchError, redact
from .sources import eligible_report, canonical_url
from .cache import digest

ATTACK_URL = 'https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json'


def words(value):
    return set(re.findall(r'[a-z][a-z0-9_-]{3,}', str(value).lower())) - {
        'unknown', 'observed', 'version', 'source', 'package', 'python', 'javascript', 'repository', 'security',
        'summary', 'technologies', 'observations', 'claim', 'components', 'questions', 'path', 'kind',
        'return', 'import', 'value', 'line', 'evidence_ids', 'research_questions', 'unknowns'}


def normalize_attack(bundle):
    objects = bundle.get('objects') if isinstance(bundle, dict) else None
    if not isinstance(objects, list):
        raise FetchError('Invalid ATT&CK STIX bundle.')
    techniques, stix_ids = {}, {}
    for obj in objects:
        if not isinstance(obj, dict) or obj.get('type') != 'attack-pattern' or obj.get('revoked') or obj.get('x_mitre_deprecated'):
            continue
        for ref in obj.get('external_references', []):
            tid = ref.get('external_id', '')
            if ref.get('source_name') == 'mitre-attack' and re.fullmatch(r'T\d{4}(?:\.\d{3})?', tid):
                techniques[tid] = {'id': tid, 'name': redact(obj.get('name', ''))[:100],
                                   'description': redact(obj.get('description', ''))[:300],
                                   'url': 'https://attack.mitre.org/techniques/' + tid.replace('.', '/') + '/',
                                   'category': 'ATT&CK technique / background mechanism',
                                   'procedures': [], 'stix_id': obj.get('id'), 'modified': obj.get('modified', 'unknown')}
                stix_ids[obj.get('id')] = tid
    for obj in objects:
        if not isinstance(obj, dict) or obj.get('type') != 'relationship' or obj.get('relationship_type') != 'uses' or obj.get('revoked'):
            continue
        tid = stix_ids.get(obj.get('target_ref'))
        if tid and len(techniques[tid]['procedures']) < 2:
            refs = [ref.get('url', '') for ref in obj.get('external_references', [])
                    if canonical_url(ref.get('url', ''))][:3]
            techniques[tid]['procedures'].append({'description': redact(obj.get('description', ''))[:240],
                                                 'references': refs,
                                                 'limitation': 'ATT&CK procedure reference, not independently retrieved incident proof.'})
    normalized = list(techniques.values())[:1500]
    return {'techniques': normalized,
            'provenance': {'url': ATTACK_URL, 'bundle_id': bundle.get('id', 'unknown'),
                           'normalized_content_hash': digest(normalized),
                           'retrieved_at': datetime.now(timezone.utc).isoformat()}}


def technique_candidates(index, profile, advisories):
    text = json.dumps(profile) + json.dumps([r['identifiers'] for r in advisories])
    explicit = set(re.findall(r'\bT\d{4}(?:\.\d{3})?\b', text))
    terms = words(text)
    ranked = sorted(index.get('techniques', []), key=lambda t: (
        t['id'] in explicit, len(terms & words(t['name'] + ' ' + t['description']))), reverse=True)
    return [t for t in ranked if t['id'] in explicit or terms & words(t['name'] + ' ' + t['description'])][:3]


def attack_mappings(incidents, candidates, known_ids=None):
    valid = set(known_ids or []) | {t['id'] for t in candidates}
    result = []
    for incident in incidents:
        # An unsupported model-written identifier is never accepted as a mapping.
        ids = sorted(set(re.findall(r'\bT\d{4}(?:\.\d{3})?\b', incident['source_quote'])) & valid)
        result.append({'incident_id': incident['id'], 'status': 'mapped' if ids else 'unmapped',
                       'technique_ids': ids, 'basis': 'Explicit technique ID in verified source passage' if ids
                       else 'No explicit supported technique identifier in the accepted passage; lexical candidates are not mappings.'})
    return result


def normalize_vcdb(record, terms, origin, retrieved_at=None):
    text = json.dumps(record, sort_keys=True)
    if not words(text) & terms:
        return None
    timeline = record.get('timeline', {}).get('incident', {})
    year = timeline.get('year')
    incident_date = 'unknown'
    try:
        observed = date(year, timeline.get('month'), timeline.get('day'))
        if observed <= date.today():
            incident_date = observed.isoformat()
    except (ValueError, TypeError):
        pass
    refs = record.get('reference', [])
    refs = refs if isinstance(refs, list) else [refs]
    return {'id': record.get('incident_id', 'unknown'), 'category': 'historical incident record',
            'summary': redact(str(record.get('summary', 'No technical summary provided.')))[:600],
            'incident_date': incident_date, 'incident_year': year, 'publication_date': 'unknown',
            'retrieved_at': retrieved_at or datetime.now(timezone.utc).isoformat(), 'provenance': origin,
            'references': [canonical_url(r) for r in refs if isinstance(r, str) and canonical_url(r)],
            'limitation': 'VCDB keyword/taxonomy match only. Technical mechanism, prerequisites, and target applicability remain unverified; sparse records cannot support a technical finding.'}


def discover_knowledge(profile, advisories, budget, enable_vcdb=False):
    limitations, references, candidates, history = [], [], [], []
    attack_provenance, attack_ids = {}, []
    try:
        index = budget.json(ATTACK_URL, dataset=True, normalize=normalize_attack)
        candidates = technique_candidates(index, profile, advisories)
        attack_provenance = index.get('provenance', {})
        attack_provenance.setdefault('normalized_content_hash', digest(index.get('techniques', [])))
        attack_ids = [technique['id'] for technique in index.get('techniques', [])]
        for technique in candidates:
            for procedure in technique['procedures']:
                for url in procedure['references']:
                    if eligible_report(url):
                        references.append({'url': url, 'title': technique['name'], 'discovered_via': ['mitre-attack'],
                                           'technique_ids': [technique['id']]})
    except (FetchError, ValueError, TypeError, KeyError, AttributeError) as exc:
        limitations.append(f'ATT&CK discovery unavailable: {exc}')
    if enable_vcdb:
        token = os.getenv('GITHUB_TOKEN', '').strip()
        if not token:
            limitations.append('VCDB discovery unavailable: GitHub code search requires GITHUB_TOKEN; no historical records fetched.')
        else:
            terms = words(' '.join(t['name'] for t in profile['technologies']))
            ids = [identifier for record in advisories for identifier in record['identifiers'] if identifier.startswith('CVE-')]
            term = ids[0] if ids else next(iter(sorted(terms)), '')
            if term:
                headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                           'X-GitHub-Api-Version': '2022-11-28'}
                try:
                    response = budget.json('https://api.github.com/search/code?' + urlencode({
                        'q': f'repo:vz-risk/VCDB path:data/json/validated {term}', 'per_page': 3}), headers=headers)
                    for item in response.get('items', [])[:3]:
                        sha, path = item.get('sha', ''), item.get('path', '')
                        if not re.fullmatch(r'[0-9a-f]{40}', sha) or not re.fullmatch(r'data/json/validated/[\w.-]+\.json', path):
                            continue
                        origin = f'https://api.github.com/repos/vz-risk/VCDB/git/blobs/{sha}'
                        blob = budget.json(origin, headers=headers)
                        if blob.get('encoding') != 'base64' or len(blob.get('content', '')) > 250000:
                            continue
                        raw = json.loads(base64.b64decode(blob['content'], validate=False))
                        record = normalize_vcdb(raw, terms | words(term), origin,
                                                getattr(budget, 'retrieval_times', {}).get(origin))
                        if record:
                            history.append(record)
                            references.extend({'url': url, 'title': record['summary'][:120], 'discovered_via': ['vcdb']}
                                              for url in record['references'] if eligible_report(url))
                    limitations.append('VCDB coverage: one keyword query and at most three official records; not exhaustive historical discovery.')
                except (FetchError, ValueError, TypeError, KeyError, AttributeError) as exc:
                    limitations.append(f'VCDB discovery unavailable: {exc}')
    else:
        limitations.append('VCDB historical discovery disabled; set ENABLE_VCDB=1 to opt in.')
    return {'techniques': candidates, 'attack_provenance': attack_provenance, 'attack_ids': attack_ids, 'historical_records': history,
            'references': references, 'limitations': limitations}
