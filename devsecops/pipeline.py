import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .agents import ModelClient, analyze_repository, research_incidents, review_security, answer_followup
from .config import MAX_JOB_SECONDS, ROLE_MODELS, missing_credentials
from .demo import fixture
from .evidence import render_report, validate_profile, validate_research, validate_review
from .repository import inspect_repo


class Cancelled(Exception):
    pass


class Runner:
    def __init__(self, store, demo_delay=0.7):
        self.store = store
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='review')
        self.demo_delay = demo_delay

    def submit(self, job_id):
        return self.pool.submit(self.run, job_id)

    def run(self, job_id):
        started = time.monotonic()
        store = self.store
        job = store.get(job_id)
        stage = 'prepare'
        warnings = []

        def emit(stage, title, detail=''):
            store.emit(job_id, stage, title, detail)

        def checkpoint():
            if store.get(job_id)['status'] in ('cancelling', 'cancelled'):
                raise Cancelled()
            if time.monotonic() - started > MAX_JOB_SECONDS:
                raise ValueError('Analysis exceeded its overall time budget. Saved evidence is available; try a smaller repository.')

        def begin(name, detail):
            nonlocal stage
            checkpoint()
            stage = name
            store.stage(job_id, name, 'running')
            emit(name, 'Stage started', detail)

        def finish(name, artifact, key):
            checkpoint()
            store.artifact(job_id, key, artifact)
            store.stage(job_id, name, 'completed')
            emit(name, 'Stage completed', f'{key.title()} is available in the evidence panel')

        try:
            checkpoint()
            if not store.transition(job_id, {'queued'}, status='running'):
                checkpoint()
                return
            client = ModelClient(emit, checkpoint)
            demo = job['mode'] == 'demo'
            if not demo and missing_credentials():
                raise ValueError('Live analysis needs ' + ', '.join(missing_credentials()) + '. Configure .env and restart.')
            fixtures = fixture() if demo else None
            begin('prepare', 'Loading a labeled synthetic fixture' if demo else 'Reading a bounded, immutable public repository snapshot')
            repo = fixtures[0] if demo else inspect_repo(job['repository_url'], emit, checkpoint)
            if demo:
                emit('prepare', 'Offline example', 'Synthetic repository and incident. No live research or AI calls.')
                time.sleep(self.demo_delay)
            finish('prepare', repo, 'repository')

            begin('analyst', 'Mapping components, security-relevant behavior, and unknowns')
            profile = fixtures[1] if demo else analyze_repository(repo, client)
            profile, rejected = validate_profile(profile, repo)
            warnings.extend(rejected)
            emit('analyst', 'Repository citations checked', f"{len(profile['observations'])} accepted observations; {len(rejected)} rejected")
            if demo:
                time.sleep(self.demo_delay)
            finish('analyst', profile, 'profile')

            begin('researcher', f"Researching mechanisms; publication window: {job['days']} days")
            try:
                research = fixtures[2] if demo else research_incidents(profile, client, emit, checkpoint, job['days'])
                research, rejected = validate_research(research, job['days'], datetime.now(timezone.utc).date())
                warnings.extend(rejected)
            except (ValueError, OSError) as exc:
                research = {'incidents': [], 'sources': [], 'research_limitations': [f'Incident research incomplete: {exc}']}
                warnings.append('Incident research failed; no incident-linked recommendations can be established.')
                emit('researcher', 'Research incomplete', str(exc))
            if demo:
                time.sleep(self.demo_delay)
            finish('researcher', research, 'research')
            if not research['sources'] or any(x.startswith(('Source unavailable:', 'Search unavailable:', 'Incident research incomplete:'))
                                              for x in research['research_limitations']):
                store.stage(job_id, 'researcher', 'partial')

            begin('reviewer', 'Comparing prerequisites, checking counterevidence, and identifying uncertainty')
            if research['incidents']:
                review = fixtures[3] if demo else review_security(profile, research, client)
                if not demo and review.get('followup_requests'):
                    request = review['followup_requests'][0]
                    target = request['target']
                    emit('reviewer', 'Bounded evidence follow-up', f"{target}: {request['question']}")
                    store.stage(job_id, target, 'running')
                    answer = answer_followup(request, repo, profile, research, client)
                    valid_evidence = {o['id'] for o in profile['observations']}
                    valid_incidents = {i['id'] for i in research['incidents']}
                    answer['evidence_ids'] = [x for x in answer['evidence_ids'] if x in valid_evidence]
                    answer['incident_ids'] = [x for x in answer['incident_ids'] if x in valid_incidents]
                    store.artifact(job_id, 'followup', {'request': request, 'answer': answer})
                    store.stage(job_id, target, 'completed')
                    emit(target, 'Follow-up completed', answer['answer'])
                    review = review_security(profile, research, client, followup=answer)
                    review['followup_requests'] = []
            else:
                review = {'summary': 'No incident-linked recommendations could be established from the retrieved evidence. This is not a declaration of security.',
                          'findings': [], 'existing_defenses': [], 'rejected_matches': [],
                          'questions': ['Review source availability and provide deployment context before drawing security conclusions.'], 'followup_requests': []}
            review, rejected = validate_review(review, profile, research)
            warnings.extend(rejected)
            if demo:
                time.sleep(self.demo_delay)
            finish('reviewer', review, 'review')

            begin('validation', 'Checking evidence references and assembling the cited report')
            validation = {'checks': ['Repository quote and line-range integrity', 'Incident passage integrity',
                                      'Recommendation evidence references', 'Date normalization and recency labels'],
                          'warnings': warnings, 'model_calls': client.calls, 'tokens': client.tokens,
                          'model': 'No model — synthetic offline fixture' if demo else '; '.join(
                              f"{role}: {s['provider']}/{s['model']}" for role, s in ROLE_MODELS.items()),
                          'models': {} if demo else {role: dict(s) for role, s in ROLE_MODELS.items()},
                          'role_usage': client.role_usage, 'search_calls': client.search_calls,
                          'search_provider': 'none' if demo else 'tavily',
                          'semantic_limit': 'Reference integrity checks do not independently prove semantic correctness.'}
            finish('validation', validation, 'validation')
            report = render_report(repo, profile, research, review, warnings, demo)
            checkpoint()
            status = 'partial' if warnings or store.get(job_id)['stages']['researcher'] == 'partial' else 'completed'
            if not store.transition(job_id, {'running'}, report=report, status=status):
                checkpoint()
                return
            emit('validation', 'Report ready', f"{len(review['findings'])} recommendation(s) · {len(profile['observations'])} repository observations · {len(research['incidents'])} incident record(s)")
        except Cancelled:
            stages = {s: ('cancelled' if v == 'running' else 'skipped' if v == 'queued' else v) for s, v in store.get(job_id)['stages'].items()}
            store.update(job_id, status='cancelled', stages=stages)
            emit(stage, 'Analysis cancelled', 'Saved evidence is retained. No repository changes were made.')
        except Exception as exc:
            # Never emit request payloads, provider response bodies, headers, or credentials.
            message = str(exc) if isinstance(exc, (ValueError, OSError)) else 'Unexpected analysis error. Start a new run; saved evidence is retained.'
            stages = {s: ('failed' if v == 'running' else 'skipped' if v == 'queued' else v) for s, v in store.get(job_id)['stages'].items()}
            store.update(job_id, status='failed', stages=stages, error=message)
            emit(stage, 'Analysis stopped', message)
