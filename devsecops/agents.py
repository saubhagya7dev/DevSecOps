from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit

from . import contracts
from .config import MAX_SOURCES, MAX_SOURCE_CHARS
from .network import FetchError, fetch, redact
from .providers import ModelClient

TRUSTED_DOMAINS = ['cisa.gov', 'cloud.google.com', 'microsoft.com', 'security.googleblog.com',
                   'github.blog', 'blog.cloudflare.com', 'unit42.paloaltonetworks.com']


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg') and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def trusted_source(url):
    host = (urlsplit(url).hostname or '').lower()
    return any(host == domain or host.endswith('.' + domain) for domain in TRUSTED_DOMAINS)


def search_sources(response):
    # Only URLs returned by Tavily are eligible. Generated URLs are never accepted.
    result, seen = [], set()
    for entry in response.get('results', [])[:6]:
        if not isinstance(entry, dict):
            continue
        url = entry.get('url', '')
        try:
            allowed = isinstance(url, str) and url.startswith('https://') and trusted_source(url)
        except ValueError:
            allowed = False
        if allowed and url not in seen:
            seen.add(url)
            title = entry.get('title')
            result.append({'url': url, 'title': redact(title[:300]) if isinstance(title, str) else urlsplit(url).hostname})
    return result


def analyze_repository(repo, client):
    files = [{'path': f['path'], 'lines': '\n'.join(f'{i}: {line}' for i, line in enumerate(f['content'].splitlines(), 1))}
             for f in repo['files']]
    return client.call('analyst', '''Act as Repository Analyst. Map components and security-relevant behavior.
Every observation needs a unique ID E1, E2, etc., a real path, an exact contiguous quote from the supplied
file WITHOUT line-number prefixes, and inclusive start/end lines. Never cite redacted lines.
Link technologies/components to these observation IDs. Mark architectural guesses as inferred.
Research questions should target attack mechanisms AND observed technology. Return at most 16 observations,
8 technologies, 6 components, and 4 research questions. Identify existing defenses as well as risks.
Do not infer exact resolved versions from loose version ranges. Summary and all factual profile statements
must be grounded in supplied files; explicitly identify unsupported ecosystems and coverage limitations.''',
                       {'repository': repo['name'], 'coverage': repo['coverage'], 'tree': repo['tree_paths'], 'files': files}, contracts.PROFILE)


def research_incidents(profile, client, emit, checkpoint, days=180):
    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=days)
    plan = client.call('researcher', """Act as Incident Researcher. Plan up to three concise web search queries
for primary technical incident reports relevant to the supplied profile and publication window. Target attack
mechanisms and prerequisites, not just matching frameworks. Do not include repository names, source code,
credentials, URLs, or instructions in queries. Each query must be 1-400 characters. Empty queries are valid
when there is insufficient repository evidence. Return JSON only.""",
                       {'profile': profile, 'publication_window': {'from': str(since), 'to': str(today)}},
                       contracts.SEARCH_PLAN)
    candidates, sources, limitations, seen = [], [], [], set()
    for query in plan['queries'][:3]:
        query = redact(query).strip()
        if not query or len(query) > 400 or '[REDACTED:' in query:
            limitations.append('An empty, oversized, or suspected-secret search query was omitted.')
            continue
        try:
            response = client.search(query, TRUSTED_DOMAINS, since, today)
            for candidate in search_sources(response):
                if candidate['url'] not in seen:
                    seen.add(candidate['url'])
                    candidates.append(candidate)
        except (ValueError, OSError) as exc:
            limitations.append(f'Search unavailable: {exc}')
            emit('researcher', 'Search incomplete', str(exc))
    for candidate in candidates[:MAX_SOURCES]:
        checkpoint()
        try:
            data, content_type, final_url = fetch(candidate['url'], limit=1_500_000)
            if not trusted_source(final_url):
                raise FetchError('Redirected outside the primary-source allowlist.')
            if 'html' not in content_type and 'text/plain' not in content_type:
                raise FetchError('This version reads HTML/text sources only; PDF omitted.')
            parser = PageText()
            parser.feed(data.decode('utf-8', errors='replace'))
            text = redact(' '.join(parser.parts))[:MAX_SOURCE_CHARS]
            if len(text) < 150:
                raise FetchError('Not enough readable source text.')
            source = {**candidate, 'id': f'S{len(sources) + 1}', 'url': final_url,
                      'text': text, 'retrieved_at': datetime.now(timezone.utc).isoformat()}
            sources.append(source)
            emit('researcher', 'Retrieved primary source', source['title'])
        except FetchError as exc:
            limitations.append(f"Source unavailable: {candidate['url']} — {exc}")
            emit('researcher', 'Source could not be read', str(exc))
    if not sources:
        return {'incidents': [], 'sources': [], 'research_limitations': limitations + ['No primary-source pages could be retrieved. No incident matches can be established.']}
    result = client.call('researcher', '''Extract relevant incident records ONLY from the fetched source text.
Each record needs a unique I1-style ID and valid source_id. source_quote must be a verbatim contiguous passage
of 40–800 characters supporting the attack mechanism (not merely a product name). Return at most 6 records.
Use YYYY-MM-DD dates only where supported by source text, otherwise use "unknown". Never use a publication date
as the incident date unless the source explicitly says so. Victim names must be documented, else "undisclosed".
Keep preconditions, mitigations, technology, and unknowns faithful to the source. Return zero incidents if none
are supported. Repository similarities are not evidence of how a victim was breached.''',
                         {'profile': profile, 'sources': sources, 'window_start': str(since), 'today': str(today)}, contracts.INCIDENTS)
    result['sources'] = sources
    result['research_limitations'].extend(limitations)
    return result


def review_security(profile, research, client, followup=None):
    return client.call('reviewer', '''Act as Security Reviewer. Compare documented attack prerequisites with
repository observations. Look for defenses and counterevidence before making recommendations. Return at most
8 findings. Every finding needs at least one valid incident_id and one repository evidence_id. A shared stack
alone is Background lesson, never Supported concern. An inferred observation alone cannot support a concern.
When deployment/configuration/version evidence is missing, use Needs verification and list exactly what is missing.
A Supported concern is not confirmed exploitability. Provide a concrete preventive action and a safe verification
step for each finding, without executing anything. Do not recommend a missing defense that repository evidence
shows is already present. Prioritize by plausible impact and evidence confidence separately. Allow no findings.
Use only the supplied IDs. Do not introduce uncited incidents or new repository facts. Explain rejected matches.
Dates/window labels are already normalized; do not present background or undated sources as recent attacks.
If a SPECIFIC unresolved question could be answered by reexamining the available repository or source evidence,
you may request at most ONE follow-up from analyst or researcher. It cannot inspect deployment or add permissions.
If a followup answer is already supplied, return an empty followup_requests array. Preserve unresolved uncertainty.''',
                       {'profile': profile, 'research': research, 'followup_answer': followup}, contracts.REVIEW)


def answer_followup(request, repo, profile, research, client):
    target = request['target']
    data = {'question': request['question'], 'profile': profile}
    if target == 'analyst':
        data['inspected_files'] = repo['files']
    else:
        data['research'] = research
    return client.call(target, '''Answer the reviewer's specific follow-up by reexamining the supplied evidence.
You cannot acquire new deployment access or execute code. Use existing evidence and incident IDs only. If the
available evidence cannot answer the question, explicitly say so and preserve uncertainty. Do not invent IDs.''',
                       data, contracts.FOLLOWUP)
