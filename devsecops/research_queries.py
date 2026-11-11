"""Diverse queries derived from verified repository observations, without an LLM call."""
import re

from .network import redact

MECHANISMS = {
    'request|url|http|fetch|proxy': 'SSRF',
    'pickle|yaml|deserial': 'unsafe deserialization',
    'token|auth|session|jwt|login': 'authentication bypass',
    'upload|file|path|archive': 'path traversal',
    'sql|database|query': 'SQL injection',
    'llm|rag|prompt|agent': 'prompt injection',
    'npm|pip|package|dependency': 'software supply chain',
    'docker|kubernetes|container': 'container security misconfiguration',
}


def discovery_queries(profile, packages=()):
    names = [t['name'] for t in profile.get('technologies', []) if t.get('evidence_ids')]
    names += [p['name'] for p in packages]
    names = list(dict.fromkeys(names))
    specific = [n for n in names if n.lower() not in {'python', 'javascript', 'typescript', 'html', 'css'}]
    names = specific + [n for n in names if n not in specific]
    context = ' '.join(o['claim'] + ' ' + o.get('quote', '') for o in profile.get('observations', []))
    # README badge/reference URLs must not turn every repository into an SSRF search.
    context = re.sub(r'https?://\S+', '', context, flags=re.I)
    mechanisms = [name for pattern, name in MECHANISMS.items() if re.search(pattern, context, re.I)]
    component = next((c['name'] for c in profile.get('components', []) if c.get('evidence_ids')), '')
    anchor = names[0] if names else component
    if not anchor:
        return {'recent': [], 'historical': [], 'guidance': []}
    mechanism = mechanisms[0] if mechanisms else 'security breach'
    secondary = names[1] if len(names) > 1 else anchor
    tertiary = names[2] if len(names) > 2 else anchor
    def technology_mechanism(name):
        # Query hypotheses only; these never become repository vulnerability claims.
        for pattern, term in [(r'c\+\+|rust', 'memory safety'), (r'yaml|numpy|pickle', 'unsafe deserialization'),
                              (r'react|vue|angular', 'cross site scripting'), (r'llm|rag|langchain', 'prompt injection')]:
            if re.search(pattern, name, re.I):
                return term
        return mechanism
    recent = [f'{anchor} {technology_mechanism(anchor)} incident technical analysis',
              f'{secondary} {technology_mechanism(secondary)} attack campaign postmortem']
    historical = [f'{tertiary} {technology_mechanism(tertiary)} exploited incident root cause',
                  f'{component or anchor} {mechanisms[1] if len(mechanisms) > 1 else mechanism} attack case study',
                  f'{anchor} supply chain compromise technical report']
    guidance = [f'{secondary} {technology_mechanism(secondary)} security hardening prevention guidance']
    def safe(queries):
        return list(dict.fromkeys(q[:300] for q in queries if '[REDACTED:' not in redact(q)))
    return {'recent': safe(recent), 'historical': safe(historical), 'guidance': safe(guidance)}
