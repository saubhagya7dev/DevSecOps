from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit

from . import contracts
from .context import research_profile, source_views, reviewer_views
from .config import MAX_SOURCES, MAX_SOURCE_CHARS
from .network import FetchError, fetch, redact
from .providers import ModelClient

TRUSTED_DOMAINS = ['cisa.gov', 'cloud.google.com', 'microsoft.com', 'security.googleblog.com',
                   'github.blog', 'blog.cloudflare.com', 'unit42.paloaltonetworks.com',
                   'blog.pypi.org', 'research.jfrog.com', 'wiz.io']


INCIDENT_INSTRUCTIONS = '''Extract documented EXTERNAL incident records from the supplied primary-source passages.
The target repository does NOT have to be a victim. Missing deployment/version evidence or unproven target
exposure is NEVER a reason to discard a documented external incident. The Security Reviewer, not you,
will decide whether attack prerequisites apply to the target. Shared packages or ecosystems may justify a
background lesson; extracting an incident does not claim the target was compromised. Distinguish a documented
attack from an unexploited advisory. Do not infer an incident from a normal API feature.
Each record needs a unique I1-style ID and valid source_id. source_quote must be a verbatim contiguous
passage of 40-800 characters supporting the EXTERNAL attack mechanism, copied from one supplied passage.
Return at most 3 records. Keep descriptions to one short sentence and lists to at most three short items.
Include older and undated incidents as background when relevant; the date window is a discovery preference,
not a reason to drop a supported record. Use YYYY-MM-DD dates only where supported, otherwise use "unknown".
Never substitute publication date for incident date. Victims must be documented, else use "undisclosed".
Return zero incidents only when the supplied passages document no relevant attack, advisory, or background
mechanism. Do not require evidence that the target repository is exploitable or already breached.'''

class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []
        self.main_parts, self.article_parts = [], []
        self.main_depth, self.article_depth = 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'svg', 'nav', 'footer', 'aside'):
            self.hidden += 1
        if tag == 'main':
            self.main_depth += 1
        if tag == 'article':
            self.article_depth += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg', 'nav', 'footer', 'aside') and self.hidden:
            self.hidden -= 1
        if tag == 'main':
            self.main_depth = max(0, self.main_depth - 1)
        if tag == 'article':
            self.article_depth = max(0, self.article_depth - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())
            if self.main_depth:
                self.main_parts.append(data.strip())
            if self.article_depth:
                self.article_parts.append(data.strip())

    def text(self):
        for parts in (self.article_parts, self.main_parts, self.parts):
            text = ' '.join(parts)
            if len(text) >= 150:
                return text
        return ' '.join(self.parts)


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
            # Indexes and community support threads are discovery aids, not incident analyses.
            lower_url = url.lower()
            host = (urlsplit(url).hostname or '').lower()
            if ('/news-events/bulletins/' in lower_url or '/answers/' in lower_url
                    or host == 'learn.microsoft.com' or '/microsoft-365/' in lower_url
                    or (host == 'cloud.google.com' and '/blog/' not in lower_url)
                    or (isinstance(title, str) and 'vulnerability summary for the week' in title.lower())):
                continue
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
    plan = client.call('researcher', """Act as Incident Researcher. Plan up to two concise web search queries
for primary technical incident reports relevant to the supplied profile and publication window. Target attack
mechanisms and prerequisites, not just matching frameworks. Do not include repository names, source code,
credentials, URLs, or instructions in queries. Each query must be 1-400 characters. Empty queries are valid
when there is insufficient repository evidence. Search for documented security attack mechanisms; do not invent
vulnerabilities in safe APIs or turn ordinary reliability/feature behavior into alleged attacks. Use short queries
with technology plus mechanism, without forcing a year. One query should target documented compromises or
supply-chain attacks involving an observed package; the other may target an observed security-relevant behavior.
Do not speculate that a normal function is vulnerable just because it accepts a file path. Return JSON only.""",
                       {'profile': research_profile(profile), 'publication_window': {'from': str(since), 'to': str(today)}},
                       contracts.SEARCH_PLAN, max_output_tokens=700)
    candidates, sources, limitations, seen, buckets = [], [], [], set(), []
    for query in plan['queries'][:2]:
        query = redact(query).strip()
        if not query or len(query) > 400 or '[REDACTED:' in query:
            limitations.append('An empty, oversized, or suspected-secret search query was omitted.')
            continue
        try:
            response = client.search(query, TRUSTED_DOMAINS, since, today)
            bucket = []
            for candidate in search_sources(response):
                if candidate['url'] not in seen:
                    seen.add(candidate['url'])
                    bucket.append(candidate)
            buckets.append(bucket)
        except (ValueError, OSError) as exc:
            limitations.append(f'Search unavailable: {exc}')
            emit('researcher', 'Search incomplete', str(exc))
    # Interleave queries so six hits from the first query cannot crowd out the second.
    for index in range(6):
        candidates.extend(bucket[index] for bucket in buckets if index < len(bucket))
    if not candidates and client.search_calls < 3:
        terms = ' '.join(t['name'][:60] for t in profile['technologies'][:3])
        if terms:
            try:
                emit('researcher', 'Broadening empty search', 'Searching without a date filter; older and undated results remain labeled.')
                packages = [t['name'][:60] for t in profile['technologies'][:8]
                            if t['name'].lower() not in {'python', 'javascript', 'typescript', 'html', 'css', 'sql'}]
                query = (packages[0] if packages else terms.split()[0]) + ' supply chain attack'
                response = client.search(query[:400], TRUSTED_DOMAINS, None, None)
                candidates.extend(search_sources(response))
                limitations.append('No dated candidates found; a broader undated search was used. Recency is checked from source evidence.')
            except (ValueError, OSError) as exc:
                limitations.append(f'Search unavailable: {exc}')
    for candidate in candidates[:MAX_SOURCES]:
        checkpoint()
        try:
            data, content_type, final_url = fetch(candidate['url'], limit=8_000_000)
            if not trusted_source(final_url):
                raise FetchError('Redirected outside the primary-source allowlist.')
            if 'html' not in content_type and 'text/plain' not in content_type:
                raise FetchError('This version reads HTML/text sources only; PDF omitted.')
            parser = PageText()
            parser.feed(data.decode('utf-8', errors='replace'))
            text = redact(parser.text())[:MAX_SOURCE_CHARS]
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
    limitations.append('Incident extraction reviewed selected contiguous page excerpts within a 6,000-character total text budget; full fetched text is retained.')
    try:
        result = client.call('researcher', INCIDENT_INSTRUCTIONS,
                             {'sources': source_views(sources, profile, budget=6000), 'window_start': str(since), 'today': str(today)}, contracts.INCIDENTS, max_output_tokens=2300)
    except (ValueError, OSError) as exc:
        emit('researcher', 'Incident extraction failed', str(exc))
        return {'incidents': [], 'sources': sources, 'research_limitations': limitations + [f'Incident research incomplete: {exc}'],
                'status': 'failed', 'error': str(exc)}
    result['sources'] = sources
    result['research_limitations'].extend(limitations)
    return result


def review_security(profile, research, client, followup=None):
    profile_view, research_view = reviewer_views(profile, research)
    return client.call('reviewer', '''Act as Security Reviewer. Compare documented attack prerequisites with
repository observations. Look for defenses and counterevidence before making recommendations. Return at most
4 findings. Keep descriptions to one short sentence and lists to three short items. Every finding needs at least one valid incident_id and one repository evidence_id. A shared stack
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
                       {'profile': profile_view, 'research': research_view, 'followup_answer': followup}, contracts.REVIEW)


def answer_followup(request, repo, profile, research, client):
    target = request['target']
    profile_view, research_view = reviewer_views(profile, research)
    data = {'question': request['question'], 'profile': profile_view}
    if target == 'analyst':
        data['inspected_files'] = repo['files']
    else:
        data['research'] = research_view
    return client.call(target, '''Answer the reviewer's specific follow-up by reexamining the supplied evidence.
You cannot acquire new deployment access or execute code. Use existing evidence and incident IDs only. If the
available evidence cannot answer the question, explicitly say so and preserve uncertainty. Do not invent IDs.''',
                       data, contracts.FOLLOWUP, max_output_tokens=1000)
