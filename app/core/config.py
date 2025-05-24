# Configuration settings
from pydantic import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "Subtitle Processing API"
    DATABASE_URL: str = "sqlite:///./test.db"

    class Config:
        env_file = ".env"

settings = Settings()
