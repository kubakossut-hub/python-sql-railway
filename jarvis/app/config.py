from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Baza danych
    database_url: str

    # Anthropic
    anthropic_api_key: str

    # Webhooki Make
    make2_webhook_url: str
    make9_webhook_url: str

    # Autoryzacja API
    jarvis_api_token: str

    # URL publiczny (do linków w Telegram)
    jarvis_base_url: str = "http://localhost"


settings = Settings()
