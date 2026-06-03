from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIBRETA_", env_file=".env", extra="ignore")

    # Metadata directory. Holds Libreta's own state — the git-sources registry
    # (.meta/sources.json), the watched-folders config (.meta/watched.json), and
    # the full-text search index (.libreta/search.db). It does NOT hold wiki
    # content; that lives in the git sources cloned under repos_dir.
    meta_dir: Path = Field(default=Path("./data/meta"))

    # Where git sources are cloned to. Each source gets a subdirectory named
    # by its id: <repos_dir>/<source_id>/
    repos_dir: Path = Field(default=Path("/var/lib/libreta/repos"))

    # Private SSH key files. Never committed to any repo.
    ssh_keys_dir: Path = Field(default=Path("/var/lib/libreta/ssh_keys"))

    # Gitea server credentials (one token per server, shared by every source
    # imported from it). Index of metadata + a 0600 token file per server,
    # mirroring ssh_keys_dir. Never committed to any repo.
    gitea_servers_dir: Path = Field(default=Path("/var/lib/libreta/gitea_servers"))

    # Sources config file, relative to meta_dir (reuses the .meta convention).
    sources_config: str = ".meta/sources.json"

    # Browser-facing URL for the drawio embed iframe. Must resolve in the
    # *user's browser*, not the api container — the iframe is loaded by the
    # SPA, not proxied through the api. Default matches the published host
    # port in docker-compose.yml.
    drawio_url: str = "http://localhost:8093"
