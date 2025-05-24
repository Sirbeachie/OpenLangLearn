# app/core/storage_service.py
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional # For file_obj and Optional return types
import logging
import boto3 # For S3StorageService
from botocore.exceptions import NoCredentialsError, ClientError # For S3StorageService
import shutil # For LocalStorageService
import os # For LocalStorageService

from app.core.config import settings # To access configuration like S3 details, local path, etc.

logger = logging.getLogger(__name__)

class StorageInterface(ABC):
    @abstractmethod
    async def save_file(self, file_obj: Any, destination_path: str) -> str:
        """
        Saves a file object to the storage.
        Args:
            file_obj: The file-like object to save (e.g., SpooledTemporaryFile from FastAPI).
            destination_path: The relative path or key where the file should be stored.
        Returns:
            The stored path/key (e.g., S3 key or local relative path).
        Raises:
            ConnectionError: If the storage client is not available/configured.
            IOError: For file saving errors.
        """
        pass

    @abstractmethod
    async def get_file_url(self, path: str, expiration: int = 3600) -> Optional[str]:
        """
        Gets a URL to access the file.
        Args:
            path: The path/key of the file in storage.
            expiration: Time in seconds for the URL to remain valid (mainly for S3).
        Returns:
            A string URL or None if URL generation fails or client not available.
        """
        pass

    @abstractmethod
    async def download_file_to_temp(self, path: str, temp_file_path: Path) -> None:
        """
        Downloads a file from storage to a local temporary path.
        Args:
            path: The path/key of the file in storage.
            temp_file_path: A Path object representing the local temporary file to write to.
        Raises:
            ConnectionError: If the storage client is not available/configured.
            FileNotFoundError: If the file is not found in storage.
            IOError: For other download errors.
        """
        pass

    @abstractmethod
    async def delete_file(self, path: str) -> None:
        """
        Deletes a file from storage.
        Args:
            path: The path/key of the file in storage.
        Raises:
            ConnectionError: If the storage client is not available/configured.
            FileNotFoundError: If the file is not found in storage (optional, could be idempotent).
            IOError: For other deletion errors.
        """
        pass


class S3StorageService(StorageInterface):
    def __init__(self, app_settings: Any): 
        self.bucket_name = app_settings.S3_BUCKET_NAME
        self.s3_client = None
        if not self.bucket_name:
            logger.warning("S3StorageService: S3_BUCKET_NAME is not configured. S3 operations will fail.")
            return 
        try:
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=app_settings.S3_ENDPOINT_URL,
                aws_access_key_id=app_settings.S3_ACCESS_KEY_ID,
                aws_secret_access_key=app_settings.S3_SECRET_ACCESS_KEY,
                region_name=app_settings.S3_REGION
            )
            logger.info(f"S3StorageService initialized for bucket: {self.bucket_name}")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client for S3StorageService: {e}")
            self.s3_client = None # Ensure client is None if init fails

    async def save_file(self, file_obj: Any, destination_path: str) -> str:
        if not self.s3_client:
            logger.error("S3StorageService: S3 client not initialized. Cannot save file.")
            raise ConnectionError("S3 client not initialized.")
        try:
            self.s3_client.upload_fileobj(file_obj, self.bucket_name, destination_path)
            logger.info(f"S3StorageService: Successfully uploaded to {self.bucket_name}/{destination_path}")
            return destination_path
        except ClientError as e:
            logger.error(f"S3StorageService: ClientError during S3 upload to {destination_path}: {e}")
            raise IOError(f"S3 upload failed: {e}")
        except Exception as e:
            logger.error(f"S3StorageService: Unexpected error during S3 upload to {destination_path}: {e}")
            raise IOError(f"File save operation failed unexpectedly: {e}")

    async def get_file_url(self, path: str, expiration: int = 3600) -> Optional[str]:
        if not self.s3_client:
            logger.error("S3StorageService: S3 client not initialized. Cannot get file URL.")
            return None
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Object': path},
                ExpiresIn=expiration
            )
            logger.info(f"S3StorageService: Generated presigned URL for {path}")
            return url
        except ClientError as e:
            logger.error(f"S3StorageService: ClientError generating presigned URL for {path}: {e}")
            return None
        except Exception as e: # Catch any other Boto3 or unexpected errors
            logger.error(f"S3StorageService: Unexpected error generating presigned URL for {path}: {e}")
            return None


    async def download_file_to_temp(self, path: str, temp_file_path: Path) -> None:
        if not self.s3_client:
            logger.error("S3StorageService: S3 client not initialized. Cannot download file.")
            raise ConnectionError("S3 client not initialized.")
        try:
            temp_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(temp_file_path, 'wb') as f:
                self.s3_client.download_fileobj(self.bucket_name, path, f)
            logger.info(f"S3StorageService: Successfully downloaded {path} to {temp_file_path}")
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.error(f"S3StorageService: File not found in S3: {path}")
                raise FileNotFoundError(f"File not found in S3: {path}")
            else:
                logger.error(f"S3StorageService: ClientError downloading {path}: {e}")
                raise IOError(f"S3 download failed: {e}")
        except Exception as e:
            logger.error(f"S3StorageService: Unexpected error downloading {path}: {e}")
            raise IOError(f"File download operation failed unexpectedly: {e}")

    async def delete_file(self, path: str) -> None:
        if not self.s3_client:
            logger.error("S3StorageService: S3 client not initialized. Cannot delete file.")
            raise ConnectionError("S3 client not initialized.")
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=path)
            logger.info(f"S3StorageService: Successfully deleted {path} from S3 bucket {self.bucket_name}")
        except ClientError as e:
            logger.error(f"S3StorageService: ClientError deleting {path}: {e}")
            raise IOError(f"S3 delete failed: {e}")
        except Exception as e:
            logger.error(f"S3StorageService: Unexpected error deleting {path}: {e}")
            raise IOError(f"File delete operation failed unexpectedly: {e}")


class LocalStorageService(StorageInterface):
    def __init__(self, app_settings: Any):
        self.base_path = Path(app_settings.LOCAL_STORAGE_PATH).resolve()
        # Ensure base_path directory exists (it should be created by config.py logic already)
        if not self.base_path.exists() or not self.base_path.is_dir():
            logger.warning(f"LocalStorageService: Base path {self.base_path} does not exist or is not a directory. It should have been created on startup.")
            # Depending on policy, could raise error or try to create it again.
            # For now, assume config.py handled it.
        logger.info(f"LocalStorageService initialized with base path: {self.base_path}")

    async def save_file(self, file_obj: Any, destination_path: str) -> str:
        full_path = self.base_path / destination_path
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, 'wb') as buffer:
                # Handle SpooledTemporaryFile from FastAPI by reading from its internal file
                if hasattr(file_obj, 'read'): # Check if it's a file-like object
                    shutil.copyfileobj(file_obj, buffer)
                else: # Fallback for other types, assuming it's bytes (less likely for UploadFile)
                    buffer.write(file_obj)
            logger.info(f"LocalStorageService: Successfully saved to {full_path}")
            return destination_path # Return relative path
        except IOError as e:
            logger.error(f"LocalStorageService: IOError during save to {full_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"LocalStorageService: Unexpected error during save to {full_path}: {e}")
            raise IOError(f"Local file save operation failed unexpectedly: {e}")

    async def get_file_url(self, path: str, expiration: int = 3600) -> Optional[str]:
        # For local storage, the URL is typically a path served by the application.
        # This assumes an endpoint like /api/v1/files/{filepath:path} will be set up.
        # The 'expiration' parameter is ignored for local storage.
        # Ensure the path is correctly formatted for a URL (e.g., no backslashes if on Windows)
        url_path_part = Path(path).as_posix() # Ensures forward slashes
        # This should ideally use FastAPI's URL generation for a named route if possible,
        # but for now, construct it manually.
        # This URL is relative to the API base.
        file_url = f"/api/v1/static-files/{url_path_part}" 
        logger.info(f"LocalStorageService: Generated file URL for {path}: {file_url}")
        return file_url

    async def download_file_to_temp(self, path: str, temp_file_path: Path) -> None:
        source_full_path = self.base_path / path
        if not source_full_path.exists() or not source_full_path.is_file():
            logger.error(f"LocalStorageService: File not found at {source_full_path}")
            raise FileNotFoundError(f"File not found at {source_full_path}")
        try:
            temp_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(source_full_path, 'rb') as src_f, open(temp_file_path, 'wb') as dest_f:
                shutil.copyfileobj(src_f, dest_f)
            logger.info(f"LocalStorageService: Successfully copied {source_full_path} to {temp_file_path}")
        except IOError as e:
            logger.error(f"LocalStorageService: IOError during copy from {source_full_path} to {temp_file_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"LocalStorageService: Unexpected error during copy to {temp_file_path}: {e}")
            raise IOError(f"Local file download operation failed unexpectedly: {e}")

    async def delete_file(self, path: str) -> None:
        full_path = self.base_path / path
        try:
            if full_path.exists() and full_path.is_file():
                full_path.unlink()
                logger.info(f"LocalStorageService: Successfully deleted {full_path}")
            else:
                logger.warning(f"LocalStorageService: File not found for deletion at {full_path}. Assuming already deleted.")
                # raise FileNotFoundError(f"File not found for deletion: {full_path}") # Or be idempotent
        except OSError as e: # Catching broader OS errors like permission issues
            logger.error(f"LocalStorageService: OSError deleting {full_path}: {e}")
            raise IOError(f"Local file delete failed: {e}")
        except Exception as e:
            logger.error(f"LocalStorageService: Unexpected error deleting {full_path}: {e}")
            raise IOError(f"Local file delete operation failed unexpectedly: {e}")


# Factory function to get the appropriate storage service
# This function itself is not async, but the methods of the returned service are.
from app.core.config import Settings as AppSettings # Use full type hint for clarity
# global_settings is the loaded instance from config.py
from app.core.config import settings as global_settings 

# _storage_service_instance_cache: Optional[StorageInterface] = None # Optional: Singleton cache

def get_storage_service(cfg: Optional[AppSettings] = None) -> StorageInterface:
    """
    Factory function to get the appropriate storage service.
    Can be used by FastAPI Depends() or called directly by Celery tasks.
    If cfg is None, uses the globally loaded settings.
    """
    # global _storage_service_instance_cache # Uncomment for singleton behavior
    # if _storage_service_instance_cache is not None and cfg is None: # Only use cache if global settings are used
    #     logger.debug("Returning cached StorageService instance.")
    #     return _storage_service_instance_cache

    active_settings = cfg or global_settings
    
    if active_settings.STORAGE_TYPE == "local":
        logger.debug("Initializing LocalStorageService.")
        instance = LocalStorageService(app_settings=active_settings)
    elif active_settings.STORAGE_TYPE == "s3":
        logger.debug("Initializing S3StorageService.")
        instance = S3StorageService(app_settings=active_settings)
    else:
        logger.error(f"Invalid STORAGE_TYPE: '{active_settings.STORAGE_TYPE}'. Falling back to S3.")
        instance = S3StorageService(app_settings=active_settings) # Fallback to S3
    
    # if cfg is None: # Cache only if it's the global instance
    #     _storage_service_instance_cache = instance
    # logger.info(f"StorageService instance created: {type(instance).__name__}")
    return instance


# Example of how to use the factory (e.g., in a FastAPI dependency)
# from fastapi import Depends
# async def example_usage(storage: StorageInterface = Depends(get_storage_service)):
#     await storage.save_file(...)

# Note: The old `app/core/s3_client.py` might become largely redundant if all S3 operations
# are now channeled through S3StorageService. It could be removed or its utility functions
# (if any are not covered by S3StorageService methods) could be kept for other specific uses.
# For this subtask, S3StorageService re-implements client initialization for clarity within the service.
