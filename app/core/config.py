# Configuration settings
from pydantic import BaseSettings

from dotenv import load_dotenv
import os

from dotenv import load_dotenv
import os
from pathlib import Path # Import Path
import logging # For logging directory creation

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

    # Storage Settings
    # Note: For Pydantic v1, use pattern with Field, or validate in a validator.
    # For Pydantic v2, Literal["s3", "local"] would be ideal.
    # Here, we rely on os.getenv and provide a default, with a runtime check below.
    STORAGE_TYPE: str = os.getenv("STORAGE_TYPE", "s3").lower() # Default to "s3", ensure lowercase
    LOCAL_STORAGE_PATH: Path = Path(os.getenv("LOCAL_STORAGE_PATH", "media_storage"))


    class Config:
        env_file = ".env" 
        env_file_encoding = 'utf-8'
        # Pydantic v2: extra = 'ignore' 
        # Pydantic v1: extra fields ignored by default.

settings = Settings()

# Initialize logger for config messages
config_logger = logging.getLogger(__name__)
# Ensure basicConfig is called if no other logging is set up by this point
# This is a simple setup; a more robust app would have a centralized logging config.
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=settings.LOG_LEVEL)


# Validate and ensure directory for TASK_TEMP_BASE_DIR
if not os.path.exists(settings.TASK_TEMP_BASE_DIR):
    try:
        os.makedirs(settings.TASK_TEMP_BASE_DIR, exist_ok=True)
        config_logger.info(f"Successfully created TASK_TEMP_BASE_DIR: {settings.TASK_TEMP_BASE_DIR}")
    except Exception as e:
        config_logger.error(f"Error creating TASK_TEMP_BASE_DIR {settings.TASK_TEMP_BASE_DIR}: {e}")

# Validate STORAGE_TYPE and ensure directory for LOCAL_STORAGE_PATH if type is "local"
if settings.STORAGE_TYPE not in ["s3", "local"]:
    config_logger.warning(
        f"Invalid STORAGE_TYPE: '{settings.STORAGE_TYPE}'. Must be 's3' or 'local'. Defaulting to 's3'."
    )
    settings.STORAGE_TYPE = "s3" # Fallback to a safe default

if settings.STORAGE_TYPE == "local":
    try:
        settings.LOCAL_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
        config_logger.info(f"Using local storage. Ensured directory exists at: {settings.LOCAL_STORAGE_PATH.resolve()}")
    except Exception as e:
        config_logger.error(f"Error creating LOCAL_STORAGE_PATH {settings.LOCAL_STORAGE_PATH.resolve()}: {e}")
        # Potentially raise an error or switch to a fallback storage type if local path is critical and fails
        # For now, just log the error.
