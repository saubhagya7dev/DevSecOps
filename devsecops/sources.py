"""Precise eligibility for individual original technical reports, never search snippets."""
import re
from urllib.parse import urlsplit, urlunsplit
from .network import redact

RULES = {
    'thedfirreport.com': r'/\d{4}/\d{2}/\d{2}/[^/]+/?$',
    'cloud.google.com': r'/blog/topics/(?:threat-intelligence|security)/[^/]+/?$',
    'www.microsoft.com': r'/(?:[a-z]{2}-[a-z]{2}/)?security/blog/\d{4}/\d{2}/\d{2}/[^/]+/?$',
    'msrc.microsoft.com': r'/blog/\d{4}/\d{2}/[^/]+/?$',
    'unit42.paloaltonetworks.com': r'/[^/]+/?$',
    'www.wiz.io': r'/blog/[^/]+/?$',
    'threats.wiz.io': r'/all-incidents/[^/]+/?$',
    'www.cisa.gov': r'/news-events/cybersecurity-advisories/[^/]+/?$',
    'security.googleblog.com': r'/\d{4}/\d{2}/[^/]+\.html$',
    'github.blog': r'/security/(?:[^/]+/){1,3}$',
    'blog.cloudflare.com': r'/[^/]+/?$',
    'blog.pypi.org': r'/posts/[^/]+/?$',
    'research.jfrog.com': r'/post/[^/]+/?$',
}
TRUSTED_DOMAINS = list(RULES)
EXCLUDED = {'blog', 'reports', 'research', 'security', 'index', 'feed', 'rss', 'about', 'pricing',
            'products', 'contact', 'authors', 'author', 'category', 'tag', 'tags', 'page', 'resources', 'tutorials',
            'all-articles', 'all-research', 'threat-research', 'threat-actor-groups', 'high-profile-threats',
            'threat-intelligence', 'insights', 'trend-reports', 'malware', 'vulnerabilities', 'press-releases'}


def canonical_url(url):
    try:
        p = urlsplit(url)
        if (p.scheme != 'https' or p.username or p.password or p.port not in (None, 443)
                or not p.hostname or any(c in url for c in ('\\', '\r', '\n'))):
            return ''
        host = p.hostname.lower()
        host = {'cisa.gov': 'www.cisa.gov', 'microsoft.com': 'www.microsoft.com',
                'wiz.io': 'www.wiz.io'}.get(host, host)
        return urlunsplit(('https', host, p.path.rstrip('/') or '/', '', ''))
    except (ValueError, TypeError):
        return ''


def eligible_report(url, title=''):
    url = canonical_url(url)
    if not url:
        return False
    p = urlsplit(url)
    rule = RULES.get(p.hostname)
    if not rule or not re.fullmatch(rule, p.path):
        return False
    slug = p.path.strip('/').split('/')[-1].lower()
    return (slug not in EXCLUDED and not slug.isdigit() and not re.search(r'(?:^|/)(?:tag|category|author|page|learn|tutorials?)/', p.path)
            and not re.search(r'vulnerability summary for the week|how to crop|pricing|product tutorial|customer stor|introducing |announcing |product update|1-click', title, re.I)
            and not re.search(r'\.(?:exe|dll|zip|tar|gz|bin|pt|pkl|js|json)$', slug))


def candidates(response):
    result, seen = [], set()
    for item in response.get('results', [])[:6]:
        if not isinstance(item, dict):
            continue
        title = item.get('title') if isinstance(item.get('title'), str) else ''
        url = canonical_url(item.get('url', ''))
        if url not in seen and eligible_report(url, title):
            seen.add(url)
            result.append({'url': url, 'title': redact(title[:300]) or urlsplit(url).hostname,
                           'discovered_via': ['tavily']})
    return result
