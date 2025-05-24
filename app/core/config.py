# Configuration settings
from pydantic import BaseSettings

from dotenv import load_dotenv
import os

# Load .env file before importing BaseSettings to ensure environment variables are set
load_dotenv()

class Settings(BaseSettings):
    APP_NAME: str = "Subtitle Processing API"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./test.db")

    # S3 Settings
    S3_ENDPOINT_URL: Optional[str] = os.getenv("S3_ENDPOINT_URL")
    S3_ACCESS_KEY_ID: Optional[str] = os.getenv("S3_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY: Optional[str] = os.getenv("S3_SECRET_ACCESS_KEY")
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "openlanglearn")
    S3_REGION: Optional[str] = os.getenv("S3_REGION", "us-east-1")

    # Celery Settings
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    # Task Specific Settings
    WHISPER_MODEL_NAME: str = os.getenv("WHISPER_MODEL_NAME", "base") # e.g., "tiny", "base", "small", "medium", "large"
    DEFAULT_PROCESSING_LANGUAGE: Optional[str] = os.getenv("DEFAULT_PROCESSING_LANGUAGE", "en") # Default language if not specified in request
    
    # Operational Settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    # Define a default for TASK_TEMP_BASE_DIR using tempfile.gettempdir() if not set
    TASK_TEMP_BASE_DIR: str = os.getenv("TASK_TEMP_BASE_DIR", os.path.join(os.path.realpath(os.path.dirname(__file__)), "..", "..", "task_temp_files"))

    # FastAPI Users Secret
    # Generate a strong secret key, e.g., using: openssl rand -hex 32
    FASTAPI_USERS_SECRET: str = os.getenv("FASTAPI_USERS_SECRET", "REPLACE_THIS_WITH_A_REAL_SECRET_KEY_IN_PRODUCTION")


    class Config:
        env_file = ".env" # Pydantic will also try to load this, useful for Pydantic specific .env features
        env_file_encoding = 'utf-8'
        # Pydantic v2: extra = 'ignore' # To ignore extra fields from .env not defined in Settings
        # For Pydantic v1, extra fields are ignored by default unless `extra = Extra.allow`

settings = Settings()

# Ensure TASK_TEMP_BASE_DIR exists
# Note: This will run when config.py is imported.
# Consider moving this to an application startup event if preferred.
if not os.path.exists(settings.TASK_TEMP_BASE_DIR):
    try:
        os.makedirs(settings.TASK_TEMP_BASE_DIR, exist_ok=True)
        print(f"Successfully created TASK_TEMP_BASE_DIR: {settings.TASK_TEMP_BASE_DIR}")
    except Exception as e:
        print(f"Error creating TASK_TEMP_BASE_DIR {settings.TASK_TEMP_BASE_DIR}: {e}")
