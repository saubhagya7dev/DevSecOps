import os
import re
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

from .config import MAX_FILES, MAX_FILE_BYTES, MAX_FILE_CHARS, MAX_REPO_CHARS
from .network import FetchError, fetch, get_json, redact


def parse_repo(url):
    parsed = urlsplit(url.strip())
    parts = parsed.path.strip('/').split('/')
    if (parsed.scheme != 'https' or parsed.netloc.lower() != 'github.com'
            or parsed.query or parsed.fragment or len(parts) != 2
            or not all(re.fullmatch(r'[A-Za-z0-9_.-]+', p) for p in parts)):
        raise ValueError('Enter a public repository URL such as https://github.com/owner/repository (no branch or query).')
    owner, name = parts
    name = name.removesuffix('.git')
    if not name or owner in ('.', '..') or name in ('.', '..'):
        raise ValueError('Invalid repository owner or name.')
    return owner, name


EXCLUDED = {'node_modules', 'vendor', 'dist', 'build', '.git', '.venv', 'venv', '__pycache__', 'coverage'}
SUFFIXES = {'.py', '.js', '.ts', '.tsx', '.jsx', '.go', '.rs', '.java', '.rb', '.php', '.cs', '.json', '.toml', '.yaml', '.yml', '.tf', '.md', '.txt', '.ini', '.cfg', '.sh', '.sql', '.html', '.vue', '.svelte', '.kt', '.swift', '.ex', '.exs'}


def permitted(path):
    p = PurePosixPath(path)
    name = p.name.lower()
    if any(part.lower() in EXCLUDED for part in p.parts):
        return False
    if (name.startswith('.env') or any(x in name for x in ('credential', 'secret', 'id_rsa', 'id_ed25519'))
            or p.suffix.lower() in {'.pem', '.key', '.p12', '.pfx'}):
        return False
    return p.suffix.lower() in SUFFIXES or name.startswith('readme') or name in {'dockerfile', 'makefile', 'gemfile', 'go.mod', 'go.sum', 'yarn.lock', 'poetry.lock', 'uv.lock', 'cargo.lock'}


def priority(item):
    path = item['path'].lower()
    name = PurePosixPath(path).name
    if name in {'package.json', 'pyproject.toml', 'requirements.txt', 'go.mod', 'cargo.toml', 'gemfile'}:
        return 0
    if name in {'package-lock.json', 'yarn.lock', 'poetry.lock', 'uv.lock', 'pnpm-lock.yaml'}:
        return 1
    if name.startswith('readme'):
        return 2
    if any(s in path for s in ('.github/workflows/', 'docker', 'terraform', 'auth', 'route', 'middleware', 'upload', 'fetch', 'server', 'main.', 'app.', 'settings', 'config')):
        return 3
    return 4


def inspect_repo(url, emit, checkpoint):
    owner, name = parse_repo(url)
    base = f'https://api.github.com/repos/{owner}/{name}'
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    token = os.getenv('GITHUB_TOKEN', '')
    if token:
        headers['Authorization'] = f'Bearer {token}'
    metadata = get_json(base, headers=headers)
    if metadata.get('private'):
        raise ValueError('Only public repositories are supported.')
    branch = metadata['default_branch']
    checkpoint()
    commit = get_json(base + '/commits/' + quote(branch, safe=''), headers=headers)['sha']
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('GitHub returned an invalid commit identifier.')
    emit('prepare', 'Pinned repository revision', f'{owner}/{name} at {commit[:12]}')
    tree = get_json(base + f'/git/trees/{commit}?recursive=1', headers=headers, limit=4_000_000)
    blobs = [x for x in tree.get('tree', []) if x.get('type') == 'blob' and x.get('mode') != '120000']
    candidates = sorted([x for x in blobs if permitted(x['path'])], key=lambda x: (priority(x), x['path']))
    files, skipped, total = [], [], 0
    for item in candidates:
        checkpoint()
        path = item['path']
        if len(files) >= MAX_FILES or total >= MAX_REPO_CHARS:
            skipped.append({'path': path, 'reason': 'Analysis file/context budget'})
            continue
        if item.get('size', 0) > MAX_FILE_BYTES:
            skipped.append({'path': path, 'reason': 'File exceeds size limit'})
            continue
        try:
            raw, _, _ = fetch(f'https://raw.githubusercontent.com/{owner}/{name}/{commit}/{quote(path, safe="/")}', limit=MAX_FILE_BYTES)
            if b'\x00' in raw:
                raise ValueError('Binary content')
            text = raw.decode('utf-8')
        except (FetchError, UnicodeError, ValueError) as exc:
            skipped.append({'path': path, 'reason': str(exc)})
            continue
        budget = min(MAX_FILE_CHARS, MAX_REPO_CHARS - total)
        # Keep complete lines so citations never reference partial source lines.
        prefix = text[:budget]
        truncated = len(text) > budget
        if truncated:
            prefix = prefix.rsplit('\n', 1)[0] if '\n' in prefix else ''
        content = redact(prefix)
        if not content.strip():
            skipped.append({'path': path, 'reason': 'No complete text lines within limit'})
            continue
        total += len(content)
        files.append({'path': path, 'content': content, 'truncated': truncated,
                      'url': f'https://github.com/{owner}/{name}/blob/{commit}/{quote(path, safe="/")}'})
        emit('prepare', 'Read repository file', path)
    if not files:
        raise ValueError('No supported, readable source files found within the configured limits.')
    return {'url': f'https://github.com/{owner}/{name}', 'name': f'{owner}/{name}', 'commit': commit,
            'description': metadata.get('description') or '', 'language': metadata.get('language') or 'Unknown',
            'files': files, 'tree_paths': [x['path'] for x in blobs][:600], 'skipped': skipped[:300],
            'coverage': {'files_read': len(files), 'files_in_tree': len(blobs), 'eligible_files': len(candidates),
                         'files_skipped_by_budget_or_error': len(skipped),
                         'truncated_files': sum(x['truncated'] for x in files),
                         'tree_truncated': bool(tree.get('truncated')), 'characters_read': total}}
