from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIBRETA_", env_file=".env", extra="ignore")

    # Legacy content dir — still used by the watched-folder config store and
    # the search index. Will be phased out as sources take over.
    content_dir: Path = Field(default=Path("./data/content"))

    # Where git sources are cloned to. Each source gets a subdirectory named
    # by its id: <repos_dir>/<source_id>/
    repos_dir: Path = Field(default=Path("/var/lib/libreta/repos"))

    # Private SSH key files. Never committed to any repo.
    ssh_keys_dir: Path = Field(default=Path("/var/lib/libreta/ssh_keys"))

    # Sources config file, relative to content_dir (reuses the _meta convention).
    sources_config: str = "_meta/sources.json"

    drawio_url: str = "http://drawio:8080"
