from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://paprika:paprika@db:5432/paprika"
    secret_key: str
    admin_password: str
    cookie_secure: bool = False
    session_days: int = 30
    data_dir: Path = Path("/data")
    seed_demo: bool = False
    business_name: str = "פפריקה פירות וירקות"

    # Public address of the site (e.g. https://paprika-fruits.netlify.app). Grow redirects
    # customers there and sends its server-to-server notifications to <public_url>/api/grow/...
    public_url: str = ""

    # "mock" simulates Grow end to end; "live" talks to Grow (sandbox or production by base URL).
    grow_mode: Literal["mock", "live"] = "mock"
    # Sandbox: https://sandbox.meshulam.co.il/api/light/server/1.0
    # Production: https://secure.meshulam.co.il/api/light/server/1.0
    grow_base_url: str = ""
    grow_user_id: str = ""
    grow_page_code: str = ""
    grow_api_key: str = ""
    # Secret in our webhook URLs, so only Grow (who got the URL from us) can call them.
    grow_webhook_key: str = ""

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, v: str) -> str:
        # Hosted Postgres (Neon, Render) hands out postgres:// or postgresql:// URLs.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v.removeprefix(prefix)
        return v


settings = Settings()
