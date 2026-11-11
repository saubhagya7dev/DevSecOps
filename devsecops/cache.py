"""Bounded, expiring JSON cache; no credentials are stored in keys or values."""
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path

from .config import DATA, RESEARCH_CACHE_TTL


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ResearchCache:
    def __init__(self, root=None, ttl=RESEARCH_CACHE_TTL):
        self.root = Path(root) if root is not None else DATA / 'research-cache'
        self.ttl = ttl

    def get(self, key):
        path = self.root / (digest(key) + '.json')
        try:
            if path.stat().st_size > 2_000_000 or time.time() - path.stat().st_mtime > self.ttl:
                return None
            value = json.loads(path.read_text(encoding='utf-8'))
            return value['value'] if value.get('key') == digest(key) else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def put(self, key, value):
        body = json.dumps({'key': digest(key), 'value': value}, ensure_ascii=False)
        if len(body.encode()) > 2_000_000:
            return
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            target = self.root / (digest(key) + '.json')
            temporary = target.with_suffix(f'.{os.getpid()}.{uuid.uuid4().hex}.tmp')
            temporary.write_text(body, encoding='utf-8')
            temporary.replace(target)
            entries = sorted(self.root.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
            # At most 64 x 2 MB. Normalized records only, never full STIX bundles.
            for entry in entries[64:]:
                entry.unlink(missing_ok=True)
        except OSError:
            # Cache availability never establishes source or model availability.
            pass

    def entries(self):
        if self.root.is_symlink():
            raise ValueError('Research cache folder must not be a symbolic link.')
        root = self.root.resolve()
        if not root.exists():
            return []
        return [p for p in root.iterdir() if re.fullmatch(r'[a-f0-9]{64}(?:\.\d+(?:\.[a-f0-9]{32})?\.tmp|\.json)', p.name)
                and not p.is_symlink() and p.is_file() and p.resolve().parent == root]

    def storage_stats(self):
        entries = self.entries()
        return {'files': len(entries), 'bytes': sum(p.stat().st_size for p in entries)}

    def clear(self):
        entries = self.entries()
        for path in entries:
            path.unlink(missing_ok=True)
        return {'files': len(entries)}
