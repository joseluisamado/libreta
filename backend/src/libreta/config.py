from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIBRETA_", env_file=".env", extra="ignore")

    content_dir: Path = Field(default=Path("./data/content"))
    drawio_url: str = "http://drawio:8080"
    remote_url: str | None = None
