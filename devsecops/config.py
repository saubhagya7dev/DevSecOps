import os
from dataclasses import dataclass
from types import MappingProxyType
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            key, sep, value = line.strip().partition('=')
            if sep and key and not key.startswith('#'):
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


DATA = ROOT / '.devsecops'
ROLE_MODELS = {
    'analyst': {'provider': 'gemini', 'model': 'gemini-3.5-flash-lite', 'credential': 'GEMINI_API_KEY'},
    'researcher': {'provider': 'groq', 'model': 'qwen/qwen3.8-27b', 'credential': 'GROQ_API_KEY'},
    'reviewer': {'provider': 'groq', 'model': 'openai/gpt-oss-120b', 'credential': 'GROQ_API_KEY'},
}


def missing_credentials():
    return [key for key in ('GEMINI_API_KEY', 'GROQ_API_KEY', 'TAVILY_API_KEY')
            if not os.getenv(key, '').strip()]


def provider_configuration():
    # Public metadata only; never expose credential values to the browser.
    return {'roles': {role: dict(settings) for role, settings in ROLE_MODELS.items()},
            'search_provider': 'tavily', 'missing_credentials': missing_credentials(),
            'researcher_token_budget': RESEARCHER_TOKEN_BUDGET, 'vcdb_enabled': ENABLE_VCDB,
            'live_ready': not missing_credentials()}


MAX_FILES = 36
MAX_FILE_BYTES = 64_000
MAX_FILE_CHARS = 9_000
MAX_REPO_CHARS = 100_000
MAX_SOURCES = 6
MAX_SOURCE_CHARS = 18_000
MAX_JOB_SECONDS = 900
MAX_QUEUE_SECONDS = 900
# Discovery has separate budgets; none increase model/search/page-fetch ceilings.
MAX_DISCOVERY_REQUESTS = 12
MAX_DATASET_DOWNLOADS = 2
MAX_DISCOVERY_RECORDS = 24
RESEARCHER_TOKEN_BUDGET = 1000
RESEARCH_CACHE_TTL = 86400
ENABLE_VCDB = False
STAGES = ['prepare', 'analyst', 'researcher', 'reviewer', 'validation']


@dataclass(frozen=True)
class Settings:
    role_models: Mapping
    researcher_token_budget: int
    vcdb_enabled: bool


def read_settings(environ=None):
    """Pure settings parsing; importing this module never reads a local .env file."""
    environ = os.environ if environ is None else environ
    defaults = {'analyst': ('gemini', 'gemini-3.5-flash-lite', 'GEMINI_API_KEY'),
                'researcher': ('groq', 'qwen/qwen3.8-27b', 'GROQ_API_KEY'),
                'reviewer': ('groq', 'openai/gpt-oss-120b', 'GROQ_API_KEY')}
    roles = {role: MappingProxyType({'provider': provider,
             'model': environ.get(role.upper() + '_MODEL', default), 'credential': credential})
             for role, (provider, default, credential) in defaults.items()}
    try:
        budget = int(environ.get('RESEARCHER_TOKEN_BUDGET', '1000'))
    except (ValueError, TypeError) as exc:
        raise ValueError('RESEARCHER_TOKEN_BUDGET must be a positive integer.') from exc
    if budget <= 0:
        raise ValueError('RESEARCHER_TOKEN_BUDGET must be a positive integer.')
    return Settings(MappingProxyType(roles), budget, environ.get('ENABLE_VCDB', '0') == '1')


def configure():
    """Startup only: call before importing provider/workflow modules."""
    global RESEARCHER_TOKEN_BUDGET, ENABLE_VCDB
    load_env()
    settings = read_settings()
    ROLE_MODELS.clear()
    ROLE_MODELS.update({role: dict(value) for role, value in settings.role_models.items()})
    RESEARCHER_TOKEN_BUDGET = settings.researcher_token_budget
    ENABLE_VCDB = settings.vcdb_enabled
    return settings
