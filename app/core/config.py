from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    reco_host: str = "0.0.0.0"
    # Railway injecte PORT ; RECO_PORT reste le fallback local / Docker
    reco_port: int = Field(default=8000, validation_alias=AliasChoices("RECO_PORT", "PORT"))
    reco_log_level: str = "info"
    reco_internal_api_key: str | None = None
    reco_dry_run: bool = False
    # False (défaut prod) : pas de fallback heuristique silencieux — erreur explicite si LLM KO
    reco_allow_heuristic_fallback: bool = False
    reco_llm_pass1_attempts: int = 2
    # Pause entre étapes LLM de l'orchestrateur (réduit rafales 429 Cerebras)
    reco_llm_step_delay_ms: int = 800

    supabase_url: str | None = None
    supabase_service_role_key: str | None = None

    jina_api_key: str | None = None
    jina_embedding_model: str = "jina-embeddings-v3"

    cerebras_api_key: str | None = None
    cerebras_model: str = "qwen-3-235b-a22b-instruct-2507"
    cerebras_model_fallback: str = "gpt-oss-120b"

    groq_api_key: str | None = None
    groq_model: str = "qwen/qwen3-32b"
    groq_model_fallback: str = "llama-3.3-70b-versatile"

    catalog_filter_path: str | None = None
    # Origines CORS autorisées (séparées par des virgules)
    reco_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    openrouter_api_key: str | None = None
    llm_default_model: str = "llama-3.3-70b-versatile"


def get_settings() -> Settings:
    """Recharge .env à chaque appel (évite un cache vide après création du fichier)."""
    return Settings()
