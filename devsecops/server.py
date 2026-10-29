"""Loopback-only local API and static UI, using the Python standard library."""
import json
import mimetypes
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .config import ROOT, missing_credentials, provider_configuration
from .demo import DEMO_URL
from .pipeline import Runner
from .repository import parse_repo
from .store import Store

TERMINAL = {'completed', 'partial', 'failed', 'cancelled'}


def make_handler(store, runner, token):
    submission_lock = threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, fmt, *args):
            # Avoid logging user-provided URL/query data or headers.
            pass

        def trusted_request(self):
            hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if self.headers.get('Host') not in hosts:
                return False
            origin = self.headers.get('Origin')
            return (not origin or origin in {'http://' + h for h in hosts}) and self.headers.get('Sec-Fetch-Site') != 'cross-site'

        def security_headers(self):
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header('Cache-Control', 'no-store')

        def send(self, status, data, content_type='application/json; charset=utf-8', attachment=None):
            body = json.dumps(data).encode('utf-8') if content_type.startswith('application/json') else data.encode('utf-8') if isinstance(data, str) else data
            self.send_response(status)
            self.security_headers()
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            # Rejected POSTs may have unread bodies; never reuse that connection.
            self.send_header('Connection', 'close')
            self.close_connection = True
            if attachment:
                self.send_header('Content-Disposition', f'attachment; filename="{attachment}"')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.trusted_request():
                return self.send(403, {'error': 'Only same-origin loopback requests are allowed.'})
            route = urlsplit(self.path)
            if route.path == '/api/config':
                return self.send(200, {**provider_configuration(),
                                       'token': token, 'demo_url': DEMO_URL})
            if route.path == '/api/jobs':
                return self.send(200, store.list())
            match = re.fullmatch(r'/api/jobs/([a-f0-9]{32})(?:/(events|report|artifacts))?', route.path)
            if match:
                job_id, resource = match.groups()
                job = store.get(job_id)
                if not job:
                    return self.send(404, {'error': 'Analysis not found.'})
                if resource == 'report':
                    if not job['report']:
                        return self.send(409, {'error': 'Report is not ready.'})
                    return self.send(200, job['report'], 'text/markdown; charset=utf-8', 'repository-threat-review.md')
                if resource == 'artifacts':
                    return self.send(200, job['artifacts'], attachment='review-evidence.json')
                if resource == 'events':
                    try:
                        after = int(self.headers.get('Last-Event-ID') or parse_qs(route.query).get('after', ['0'])[0])
                    except ValueError:
                        return self.send(400, {'error': 'Invalid event cursor.'})
                    self.send_response(200)
                    self.security_headers()
                    self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.close_connection = True
                    try:
                        for _ in range(120):
                            events = store.events(job_id, after)
                            for event in events:
                                after = event['seq']
                                self.wfile.write(f"id: {after}\nevent: activity\ndata: {json.dumps(event)}\n\n".encode())
                            self.wfile.write(b': heartbeat\n\n')
                            self.wfile.flush()
                            if store.get(job_id)['status'] in TERMINAL and not store.events(job_id, after):
                                self.wfile.write(b'event: finished\ndata: {}\n\n')
                                self.wfile.flush()
                                break
                            time.sleep(0.7)
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass
                    return
                return self.send(200, job)
            paths = {'/': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css', '/favicon.svg': 'favicon.svg'}
            if route.path in paths:
                path = ROOT / 'web' / paths[route.path]
                return self.send(200, path.read_bytes(), mimetypes.guess_type(path)[0] or 'application/octet-stream')
            return self.send(404, {'error': 'Not found.'})

        def do_POST(self):
            if not self.trusted_request() or not secrets.compare_digest(self.headers.get('X-Review-Token', ''), token):
                return self.send(403, {'error': 'Invalid local request token. Reload the page.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    return self.send(413, {'error': 'Request body is empty or too large.'})
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('Expected a JSON object.')
                if self.path == '/api/jobs':
                    mode = data.get('mode', 'live')
                    if mode not in ('live', 'demo'):
                        raise ValueError('Choose live analysis or offline example.')
                    repo = DEMO_URL if mode == 'demo' else data.get('repository_url', '')
                    if not isinstance(repo, str):
                        raise ValueError('Repository URL must be text.')
                    owner, name = parse_repo(repo)
                    if mode == 'live' and missing_credentials():
                        return self.send(409, {'error': 'Set ' + ', '.join(missing_credentials()) + ' in .env and restart the server. The offline example is available now.'})
                    days = data.get('days', 180)
                    if type(days) is not int or not 7 <= days <= 730:
                        raise ValueError('Research window must be between 7 and 730 days.')
                    with submission_lock:
                        if sum(j['status'] in ('queued', 'running', 'cancelling') for j in store.list()) >= 5:
                            return self.send(429, {'error': 'Analysis queue is full. Wait for a job to finish.'})
                        job = store.create(f'https://github.com/{owner}/{name}', mode, days)
                        store.emit(job['id'], 'prepare', 'Analysis queued', 'One worker processes reviews in order; closing the page does not cancel the job.')
                        runner.submit(job['id'])
                    return self.send(202, {'id': job['id']})
                match = re.fullmatch(r'/api/jobs/([a-f0-9]{32})/cancel', self.path)
                if match:
                    job = store.get(match[1])
                    if not job:
                        return self.send(404, {'error': 'Analysis not found.'})
                    if store.transition(job['id'], {'queued', 'running'}, status='cancelling'):
                        store.emit(job['id'], 'prepare', 'Cancellation requested', 'The current network/model call may finish before the worker stops.')
                    return self.send(200, {'status': store.get(job['id'])['status']})
                return self.send(404, {'error': 'Not found.'})
            except (ValueError, TypeError, UnicodeError):
                return self.send(400, {'error': 'Invalid request. Use a public GitHub repository URL and a supported research window.'})

    return Handler


def serve(port=8765):
    store = Store()
    store.recover()
    runner = Runner(store)
    handler = make_handler(store, runner, secrets.token_urlsafe(32))
    server = ThreadingHTTPServer(('127.0.0.1', port), handler)
    server.daemon_threads = True
    print(f'DevSecOps is running at http://127.0.0.1:{server.server_port}', flush=True)
    print('Live analysis configured.' if not missing_credentials() else
          'Offline example available. Configure ' + ', '.join(missing_credentials()) + ' in .env for live analysis.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        runner.pool.shutdown(wait=False, cancel_futures=True)
