"""Read package declarations from already inspected files; never resolve or execute a project."""
import json
import re
import tomllib


def normalize_name(name, ecosystem):
    return re.sub(r'[-_.]+', '-', name).lower() if ecosystem == 'PyPI' else name.lower()


def package_inventory(repo, profile=None):
    packages, limitations = [], []

    def add(name, ecosystem, spec='', resolved=False, path=''):
        name = normalize_name(name, ecosystem)
        if not re.fullmatch(r'(?:@[a-z0-9_.-]+/)?[a-z0-9_.-]+', name):
            return
        exact = bool(re.fullmatch(r'\d[\w.+!-]*', spec))
        packages.append({'name': name, 'ecosystem': ecosystem, 'version': spec if exact else None,
                         'version_kind': 'lockfile resolution' if resolved and exact else
                         'exact declaration' if exact else 'range or unknown',
                         'declaration': spec[:120], 'path': path,
                         'exposure': 'Installed/deployed version and reachability are not established.'})

    def requirement(value, path):
        m = re.match(r'^\s*([\w.-]+)(?:\[[^]]+\])?\s*(.*)', value)
        if m:
            spec = m[2].split(';')[0].strip()
            add(m[1], 'PyPI', spec[2:] if spec.startswith('==') and not spec.startswith('===') else spec, path=path)

    for file in (repo or {}).get('files', []):
        path, text = file['path'], file['content']
        try:
            if path.endswith('package-lock.json'):
                data = json.loads(text)
                for key, value in data.get('packages', {}).items():
                    if 'node_modules/' in key and isinstance(value, dict):
                        add(key.rsplit('node_modules/', 1)[1], 'npm', value.get('version', ''), True, path)
            elif path.endswith('package.json'):
                data = json.loads(text)
                for field in ('dependencies', 'devDependencies', 'optionalDependencies'):
                    for name, spec in data.get(field, {}).items():
                        if isinstance(spec, str):
                            add(name, 'npm', spec, path=path)
            elif path.endswith(('requirements.txt', 'requirements-dev.txt')):
                for line in text.splitlines():
                    if line.strip() and not line.lstrip().startswith(('#', '-', '[')):
                        requirement(line, path)
            elif path.endswith(('pyproject.toml', 'poetry.lock', 'uv.lock')):
                data = tomllib.loads(text)
                if path.endswith('pyproject.toml'):
                    for value in data.get('project', {}).get('dependencies', []):
                        requirement(value, path)
                    for name, spec in data.get('tool', {}).get('poetry', {}).get('dependencies', {}).items():
                        if name != 'python' and isinstance(spec, str):
                            add(name, 'PyPI', spec, path=path)
                else:
                    for value in data.get('package', []):
                        add(value['name'], 'PyPI', value.get('version', ''), True, path)
        except (ValueError, TypeError, AttributeError, KeyError):
            limitations.append(f'Could not parse bounded or truncated package manifest: {path}.')
    selected = {}
    for package in sorted(packages, key=lambda p: (p['version_kind'] != 'lockfile resolution', p['version'] is None)):
        selected.setdefault((package['ecosystem'], package['name']), package)
    technologies = ' '.join(t['name'] for t in (profile or {}).get('technologies', [])).lower()
    named = set(re.findall(r'[@a-z0-9_./-]+', technologies))
    ranked = sorted(selected.values(), key=lambda p: (
        p['name'] not in named, p['version_kind'] != 'lockfile resolution', p['version'] is None, p['name']))
    if len(ranked) > 24:
        limitations.append('Package inventory limited to 24 entries from inspected files.')
    limitations.append('Package coverage is limited to inspected npm and Python manifests; dependency ranges are not resolved or installed versions.')
    return ranked[:24], limitations
