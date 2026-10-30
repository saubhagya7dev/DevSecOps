from html.parser import HTMLParser

from . import contracts
from .context import reviewer_views
from .network import fetch
from .providers import ModelClient
from .sources import TRUSTED_DOMAINS, eligible_report as trusted_source, candidates as search_sources
from .discovery import discover_structured

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


def research_incidents(profile, client, emit, checkpoint, days=180, repo=None):
    from .incident_research import run_research
    return run_research(profile, client, emit, checkpoint, days, repo, discover_structured,
                        fetch, PageText, INCIDENT_INSTRUCTIONS)


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
