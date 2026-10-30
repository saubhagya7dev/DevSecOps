"""Bounded structured discovery. Advisories and knowledge records never prove an attack."""
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlencode, urlsplit

from .cache import ResearchCache
from .config import MAX_DISCOVERY_REQUESTS, MAX_DATASET_DOWNLOADS, MAX_DISCOVERY_RECORDS, ENABLE_VCDB
from .network import FetchError, get_json, redact
from .packages import package_inventory, normalize_name
from .sources import canonical_url, eligible_report


class DiscoveryBudget:
    def __init__(self, checkpoint, cache=None, emit=None):
        self.checkpoint, self.cache = checkpoint, cache or ResearchCache()
        self.requests, self.datasets, self.cache_hits = 0, 0, 0
        self.retries = 0
        self.retrieval_times = {}
        self.emit = emit or (lambda *args: None)

    def json(self, url, *, body=None, headers=None, dataset=False, normalize=None):
        self.checkpoint()
        # Credentials are intentionally excluded from keys. All data is public.
        key = ['discovery-v1', url, body]
        cached = self.cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            self.emit('researcher', 'Structured cache hit', urlsplit(url).hostname or 'official source')
            if isinstance(cached, dict) and cached.get('_discovery_cache') == 1:
                if not isinstance(cached.get('retrieved_at'), str) or 'payload' not in cached:
                    raise FetchError('Malformed structured cache entry; no cached evidence accepted.')
                self.retrieval_times[url] = cached['retrieved_at']
                return cached['payload']
            provenance = cached.get('provenance') if isinstance(cached, dict) else None
            self.retrieval_times[url] = provenance.get('retrieved_at', 'unknown (legacy cache)') if isinstance(provenance, dict) else 'unknown (legacy cache)'
            return cached
        if self.requests >= MAX_DISCOVERY_REQUESTS or (dataset and self.datasets >= MAX_DATASET_DOWNLOADS):
            raise FetchError('Structured discovery request/dataset budget exhausted.')
        for attempt in range(2):
            self.checkpoint()
            if self.requests >= MAX_DISCOVERY_REQUESTS:
                raise FetchError('Structured discovery request budget exhausted.')
            self.requests += 1
            self.emit('researcher', 'Loading official dataset' if dataset else 'Querying structured source',
                      f'{urlsplit(url).hostname} · request {self.requests}/{MAX_DISCOVERY_REQUESTS}')
            if dataset:
                if self.datasets >= MAX_DATASET_DOWNLOADS:
                    raise FetchError('Structured dataset download budget exhausted.')
                self.datasets += 1
            try:
                request_headers = dict(headers or {})
                if body is not None:
                    request_headers.setdefault('Content-Type', 'application/json')
                value = get_json(url, headers=request_headers, body=json.dumps(body).encode() if body is not None else None,
                                 timeout=45, limit=64_000_000 if dataset else 2_000_000, redirects=0)
                self.checkpoint()
                acquired = datetime.now(timezone.utc).isoformat()
                value = normalize(value) if normalize else value
                self.retrieval_times[url] = acquired
                self.cache.put(key, {'_discovery_cache': 1, 'retrieved_at': acquired, 'payload': value})
                return value
            except FetchError as exc:
                if (attempt or self.retries >= 1 or exc.status not in (429, 503) or exc.daily_limit
                        or exc.retry_after is None or exc.retry_after > 30):
                    raise
                self.retries += 1
                deadline = time.monotonic() + exc.retry_after
                while time.monotonic() < deadline:
                    self.checkpoint()
                    time.sleep(min(0.25, max(0, deadline - time.monotonic())))


def identifiers(values):
    return sorted({x.upper() for value in values if isinstance(value, str)
                   for x in re.findall(r'CVE-\d{4}-\d{4,}|GHSA-[\w]{4}-[\w]{4}-[\w]{4}|(?:PYSEC|OSV)-[\w-]+', value, re.I)})


def normalize_advisory(raw, package, provider, retrieved_at=None):
    if not isinstance(raw, dict) or raw.get('withdrawn') or raw.get('withdrawn_at'):
        return None
    gh = provider == 'github'
    affected = raw.get('vulnerabilities' if gh else 'affected', [])
    matches = []
    fixed, ranges = [], []
    for entry in affected[:40]:
        p = entry.get('package', {})
        ecosystem = {'pip': 'PyPI', 'npm': 'npm'}.get(p.get('ecosystem'), p.get('ecosystem'))
        if ecosystem != package['ecosystem'] or normalize_name(p.get('name', ''), ecosystem) != package['name']:
            continue
        matches.append(entry)
        if gh:
            ranges.append(entry.get('vulnerable_version_range', 'unknown'))
            patched = entry.get('first_patched_version')
            if isinstance(patched, str):
                fixed.append(patched)
            elif isinstance(patched, dict) and patched.get('identifier'):
                fixed.append(patched['identifier'])
        else:
            ranges.extend(entry.get('ranges', [])[:4])
            fixed.extend(event['fixed'] for r in entry.get('ranges', [])[:4] for event in r.get('events', []) if 'fixed' in event)
    if not matches:
        return None
    record_id = raw.get('ghsa_id' if gh else 'id', '')
    acquired = retrieved_at or datetime.now(timezone.utc).isoformat()
    published = str(raw.get('published_at' if gh else 'published', 'unknown'))[:10]
    ids = identifiers([record_id, raw.get('cve_id', '')] + raw.get('aliases', []) +
                      [entry.get('value', '') for entry in raw.get('identifiers', [])])
    refs = [r.get('url') if isinstance(r, dict) else r for r in raw.get('references', [])[:30]]
    refs = sorted({canonical_url(r) for r in refs if isinstance(r, str) and canonical_url(r)})
    return {'id': record_id, 'category': 'vulnerability advisory', 'identifiers': ids,
            'title': redact(str(raw.get('summary', record_id)))[:400], 'package': package,
            'version_assessment': 'Provider query for exact declared/resolved version; production installation unverified.'
                                  if package['version'] else 'Package-name match only; unresolved range/version. Applicability unknown.',
            'affected_ranges': ranges[:4], 'fixed_versions': sorted(set(fixed))[:8], 'references': refs,
            'publication_date': published,
            'incident_date': 'unknown', 'retrieved_at': acquired,
            'provenance': [{'provider': provider, 'record_id': record_id,
                            'publication_date': published, 'retrieved_at': acquired,
                            'url': (canonical_url(raw.get('html_url', '')) or 'https://github.com/advisories/' + quote(record_id, safe=''))
                            if gh else 'https://osv.dev/vulnerability/' + quote(record_id, safe='')}],
            'limitation': 'An affected package or advisory does not establish an observed attack or target exposure.'}


def deduplicate_advisories(records):
    result = []
    for record in records:
        if not record:
            continue
        ids = set(record['identifiers']) or {record['id']}
        overlaps = [r for r in result if (set(r['identifiers']) or {r['id']}) & ids
                    and r['package']['name'] == record['package']['name']
                    and r['package']['ecosystem'] == record['package']['ecosystem']]
        merged = dict(record)
        for old in overlaps:
            result.remove(old)
            for field in ('identifiers', 'references', 'fixed_versions'):
                merged[field] = sorted(set(merged[field] + old[field]))
            ranges = {json.dumps(value, sort_keys=True): value for value in merged['affected_ranges'] + old['affected_ranges']}
            merged['affected_ranges'] = list(ranges.values())[:8]
            merged['provenance'] += old['provenance']
        result.append(merged)
    return result[:MAX_DISCOVERY_RECORDS]


def discover_structured(repo, profile, checkpoint, emit, budget=None):
    from .knowledge import discover_knowledge
    budget = budget or DiscoveryBudget(checkpoint, emit=emit)
    packages, limitations = package_inventory(repo, profile)
    records, references = [], []
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if os.getenv('GITHUB_TOKEN', '').strip():
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN'].strip()
    for package in packages[:3]:
        checkpoint()
        query = {'package': {'name': package['name'], 'ecosystem': package['ecosystem']}}
        if package['version']:
            query['version'] = package['version']
        try:
            response = budget.json('https://api.osv.dev/v1/query', body=query)
            records.extend(normalize_advisory(r, package, 'osv', budget.retrieval_times.get('https://api.osv.dev/v1/query')) for r in response.get('vulns', [])[:8])
            if response.get('next_page_token'):
                limitations.append(f'OSV pagination omitted for {package["name"]} within API budget.')
        except (FetchError, TypeError, AttributeError) as exc:
            limitations.append(f'OSV discovery unavailable: {exc}')
        params = {'ecosystem': 'pip' if package['ecosystem'] == 'PyPI' else 'npm',
                  'affects': package['name'] + ('@' + package['version'] if package['version'] else ''), 'per_page': 8}
        try:
            advisory_url = 'https://api.github.com/advisories?' + urlencode(params)
            response = budget.json(advisory_url, headers=headers)
            if not isinstance(response, list):
                raise FetchError('Unexpected global-advisory response.')
            records.extend(normalize_advisory(r, package, 'github', budget.retrieval_times.get(advisory_url)) for r in response[:8])
            if len(response) == 8:
                limitations.append(f'GitHub advisory pagination may be incomplete for {package["name"]}.')
        except (FetchError, TypeError, AttributeError) as exc:
            limitations.append(f'GitHub advisory discovery unavailable: {exc}')
    if len(packages) > 3:
        limitations.append(f'Queried three of {len(packages)} inventoried packages; remaining packages omitted by budget.')
    records = deduplicate_advisories(records)
    for record in records:
        for url in record['references']:
            if eligible_report(url):
                references.append({'url': url, 'title': record['title'], 'identifiers': record['identifiers'],
                                   'discovered_via': [p['provider'] for p in record['provenance']]})
    knowledge = discover_knowledge(profile, records, budget, ENABLE_VCDB)
    limitations.extend(knowledge.pop('limitations'))
    references.extend(knowledge.pop('references'))
    emit('researcher', 'Structured discovery complete', f'{len(records)} advisories; {budget.requests} API/dataset requests; {budget.cache_hits} cache hits')
    return {'packages': packages, 'advisories': records, **knowledge, 'references': references,
            'limitations': limitations, 'coverage': {'structured_requests': budget.requests, 'dataset_downloads': budget.datasets,
                                                   'structured_retries': budget.retries, 'cache_hits': budget.cache_hits}}
