import warnings

from pydantic_settings import BaseSettings, SettingsConfigDict

# >=32 bytes — PyJWT's InsecureKeyLengthWarning fires below that for
# HS256/SHA256. Still an obvious placeholder; a real deployment must
# override it via the JWT_SECRET env var (see the warning below).
_INSECURE_DEFAULT_JWT_SECRET = "change-me-in-production-use-a-real-secret"


class Settings(BaseSettings):
    """Env-driven config (blueprint §11.1). Field names map to the env vars
    declared in docker-compose.yml / .env.example (case-insensitive)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    database_url: str = "postgresql+psycopg://sar:sarpass@localhost:5432/sarcopilot"
    redis_url: str = "redis://localhost:6379/0"

    # Pre-declared for later parts (narrative engine) so the config surface
    # doesn't change shape when those land — unused in Part 1.
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.1:8b-instruct-q4_K_M"
    prompt_version: str = "v1.0.0"

    jwt_secret: str = _INSECURE_DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

if settings.jwt_secret == _INSECURE_DEFAULT_JWT_SECRET and settings.environment != "development":
    warnings.warn(
        "JWT_SECRET is still the insecure placeholder default outside a development "
        "environment. Set a real secret via the JWT_SECRET environment variable.",
        stacklevel=2,
    )
