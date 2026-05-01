from functools import lru_cache

from libreta.config import Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
