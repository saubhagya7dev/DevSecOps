import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            key, sep, value = line.strip().partition('=')
            if sep and key and not key.startswith('#'):
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


load_env()
DATA = ROOT / '.devsecops'
ROLE_MODELS = {
    'analyst': {'provider': 'gemini', 'model': os.getenv('ANALYST_MODEL', 'gemini-3.5-flash-lite'), 'credential': 'GEMINI_API_KEY'},
    'researcher': {'provider': 'groq', 'model': os.getenv('RESEARCHER_MODEL', 'qwen/qwen3.8-27b'), 'credential': 'GROQ_API_KEY'},
    'reviewer': {'provider': 'groq', 'model': os.getenv('REVIEWER_MODEL', 'openai/gpt-oss-120b'), 'credential': 'GROQ_API_KEY'},
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
# Discovery has separate budgets; none increase model/search/page-fetch ceilings.
MAX_DISCOVERY_REQUESTS = 12
MAX_DATASET_DOWNLOADS = 2
MAX_DISCOVERY_RECORDS = 24
RESEARCHER_TOKEN_BUDGET = int(os.getenv('RESEARCHER_TOKEN_BUDGET', '1000'))
if RESEARCHER_TOKEN_BUDGET <= 0:
    raise ValueError('RESEARCHER_TOKEN_BUDGET must be positive; the configured allowance is never raised automatically.')
RESEARCH_CACHE_TTL = 86400
ENABLE_VCDB = os.getenv('ENABLE_VCDB', '0') == '1'
STAGES = ['prepare', 'analyst', 'researcher', 'reviewer', 'validation']
