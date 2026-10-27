"""Size-bounded HTTPS with public-IP pinning, including redirect destinations."""
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit


class FetchError(ValueError):
    pass


def public_destination(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.port not in (None, 443)):
            raise FetchError('Only public HTTPS URLs on port 443 are allowed.')
        host = parsed.hostname.encode('idna').decode('ascii')
        if any(c in url for c in ('\r', '\n', '\\')):
            raise FetchError('Invalid URL.')
        addresses = list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(
            host, 443, type=socket.SOCK_STREAM)))
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise FetchError('Private, local, and reserved network destinations are blocked.')
        return parsed, host, addresses[0]
    except (ValueError, UnicodeError, OSError) as exc:
        if isinstance(exc, FetchError):
            raise
        raise FetchError('Cannot resolve a permitted public HTTPS destination.') from exc


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def fetch(url, *, headers=None, body=None, limit=2_000_000, timeout=35, redirects=3):
    method = 'POST' if body is not None else 'GET'
    request_headers = {'User-Agent': 'DevSecOps-RepositoryReview/0.1', 'Accept': '*/*'}
    request_headers.update(headers or {})
    deadline = time.monotonic() + timeout
    for hop in range(redirects + 1):
        parsed, host, address = public_destination(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError('Request deadline exceeded.')
        conn = PinnedHTTPS(host, address, min(remaining, 30))
        try:
            path = parsed.path or '/'
            if parsed.query:
                path += '?' + parsed.query
            conn.request(method, path, body=body, headers=request_headers)
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location or hop == redirects or method != 'GET':
                    raise FetchError('Redirect limit exceeded or unsafe POST redirect.')
                # Never forward authentication across redirects, even to related hosts.
                request_headers.pop('Authorization', None)
                url = urljoin(url, location)
                continue
            if response.status >= 400:
                if response.status in (401, 403, 429):
                    raise FetchError(f'Upstream HTTP {response.status}: check credentials, rate limits, or access.')
                raise FetchError(f'Upstream HTTP {response.status}.')
            if response.getheader('Content-Encoding', 'identity') != 'identity':
                raise FetchError('Compressed responses are not supported by this bounded reader.')
            length = response.getheader('Content-Length')
            if length and int(length) > limit:
                raise FetchError('Response exceeds the permitted size.')
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise FetchError('Request deadline exceeded.')
                if conn.sock:
                    conn.sock.settimeout(min(remaining, 15))
                chunk = response.read1(min(32_768, limit + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > limit:
                    raise FetchError('Response exceeds the permitted size.')
            return b''.join(chunks), response.getheader('Content-Type', ''), url
        except (OSError, http.client.HTTPException, ValueError) as exc:
            if isinstance(exc, FetchError):
                raise
            raise FetchError('Public HTTPS request failed or timed out.') from exc
        finally:
            conn.close()
    raise FetchError('Too many redirects.')


def get_json(url, **kwargs):
    data, _, _ = fetch(url, **kwargs)
    try:
        return json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise FetchError('Upstream returned invalid JSON.') from exc


SECRET = re.compile(
    r'(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{15,}|github_pat_[A-Za-z0-9_]{15,}'
    r'|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'
    r'|(?:api[_-]?key|password|secret|access[_-]?token)\s*[=:]\s*[\"\'][^\"\'\n]{8,}[\"\'])', re.I)


def redact(text):
    """Redact entire suspect lines while preserving line numbers; not a DLP guarantee."""
    result, private_key = [], False
    for line in text.splitlines():
        if re.search(r'-----BEGIN .*PRIVATE KEY-----', line):
            private_key = True
        sensitive = private_key or bool(SECRET.search(line))
        result.append('[REDACTED: suspected credential]' if sensitive else line)
        if re.search(r'-----END .*PRIVATE KEY-----', line):
            private_key = False
    return '\n'.join(result)
