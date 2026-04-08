from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    SENTRIBID_DB_URL: str = "sqlite:///./sentribid.db"
    SENTRIBID_APP_NAME: str = "SentriBiD"
    SENTRIBID_ENV: str = "dev"

settings = Settings()
