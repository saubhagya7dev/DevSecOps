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
MODEL = os.getenv('OPENAI_MODEL', 'gpt-4.1')
MAX_FILES = 36
MAX_FILE_BYTES = 64_000
MAX_FILE_CHARS = 9_000
MAX_REPO_CHARS = 100_000
MAX_SOURCES = 6
MAX_SOURCE_CHARS = 18_000
MAX_JOB_SECONDS = 900
STAGES = ['prepare', 'analyst', 'researcher', 'reviewer', 'validation']
