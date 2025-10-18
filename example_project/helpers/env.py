import pathlib
from functools import lru_cache

BASE_DIR = pathlib.Path(__file__).parent.parent
PROJECT_DIR_ENV_FILE = BASE_DIR / ".env"
REPO_ROOT_DIR_ENV_FILE = BASE_DIR.parent / ".env"


@lru_cache
def load_env():
    from decouple import Config, RepositoryEnv

    if PROJECT_DIR_ENV_FILE.exists():
        return Config(RepositoryEnv(str(PROJECT_DIR_ENV_FILE)))
    elif REPO_ROOT_DIR_ENV_FILE.exists():
        return Config(RepositoryEnv(str(REPO_ROOT_DIR_ENV_FILE)))
    from decouple import config

    return config


config = load_env()
