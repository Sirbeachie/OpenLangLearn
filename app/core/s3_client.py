import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import logging
from app.core.config import settings
from typing import Optional, BinaryIO

logger = logging.getLogger(__name__)

def get_s3_client():
    """Initializes and returns an S3 client."""
    try:
        client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            region_name=settings.S3_REGION
        )
        # Test connection by listing buckets (optional, can be slow)
        # client.list_buckets() 
        logger.info("S3 client initialized successfully.")
        return client
    except NoCredentialsError:
        logger.error("S3 credentials not found. Please configure AWS credentials.")
        return None
    except ClientError as e:
        logger.error(f"Error initializing S3 client: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during S3 client initialization: {e}")
        return None

def upload_file_to_s3(file_path_or_obj: str | BinaryIO, bucket_name: str, object_name: str, s3_client=None) -> bool:
    """
    Uploads a file or a file-like object to an S3 bucket.

    :param file_path_or_obj: Path to the file to upload or a file-like object (e.g., BytesIO).
    :param bucket_name: Bucket to upload to.
    :param object_name: S3 object name. If not specified, file_name is used.
    :param s3_client: Optional pre-configured S3 client.
    :return: True if file was uploaded, else False.
    """
    if s3_client is None:
        s3_client = get_s3_client()
    
    if s3_client is None:
        logger.error("S3 client not available for upload.")
        return False

    try:
        if isinstance(file_path_or_obj, str):
            with open(file_path_or_obj, "rb") as f:
                s3_client.upload_fileobj(f, bucket_name, object_name)
        else: # Assumed to be a file-like object
            s3_client.upload_fileobj(file_path_or_obj, bucket_name, object_name)
        logger.info(f"Successfully uploaded '{object_name}' to bucket '{bucket_name}'.")
        return True
    except FileNotFoundError:
        logger.error(f"Upload error: File not found at '{file_path_or_obj}'.")
        return False
    except NoCredentialsError:
        logger.error("Upload error: Credentials not available.")
        return False
    except ClientError as e:
        logger.error(f"Upload error: S3 ClientError: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during S3 upload: {e}")
        return False

def generate_presigned_url(bucket_name: str, object_name: str, expiration: int = 3600, s3_client=None) -> Optional[str]:
    """
    Generate a presigned URL to share an S3 object.

    :param bucket_name: Name of the S3 bucket.
    :param object_name: Name of the S3 object.
    :param expiration: Time in seconds for the presigned URL to remain valid.
    :param s3_client: Optional pre-configured S3 client.
    :return: Presigned URL as string. If error, returns None.
    """
    if s3_client is None:
        s3_client = get_s3_client()

    if s3_client is None:
        logger.error("S3 client not available for generating presigned URL.")
        return None
        
    try:
        response = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Object': object_name},
            ExpiresIn=expiration
        )
        logger.info(f"Generated presigned URL for '{object_name}' in bucket '{bucket_name}'.")
        return response
    except ClientError as e:
        logger.error(f"Error generating presigned URL: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during presigned URL generation: {e}")
        return None

def download_file_from_s3(bucket_name: str, object_name: str, destination_path: str, s3_client=None) -> bool:
    """
    Downloads a file from S3 to a local path.

    :param bucket_name: Name of the S3 bucket.
    :param object_name: Name of the S3 object (key).
    :param destination_path: Local path to save the downloaded file.
    :param s3_client: Optional pre-configured S3 client.
    :return: True if download was successful, else False.
    """
    if s3_client is None:
        s3_client = get_s3_client()

    if s3_client is None:
        logger.error("S3 client not available for download.")
        return False

    try:
        s3_client.download_file(bucket_name, object_name, destination_path)
        logger.info(f"Successfully downloaded '{object_name}' from bucket '{bucket_name}' to '{destination_path}'.")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.error(f"Download error: Object '{object_name}' not found in bucket '{bucket_name}'.")
        else:
            logger.error(f"Download error: S3 ClientError: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during S3 download: {e}")
        return False

# Example usage (optional, for direct testing of this module)
# if __name__ == "__main__":
#     # Ensure your .env file has S3 credentials or they are in your environment
#     # Create a dummy file for testing
#     with open("dummy_test_file.txt", "w") as f:
#         f.write("Hello S3 from OpenLangLearn!")

#     test_bucket = settings.S3_BUCKET_NAME
#     test_object_name = "test_uploads/dummy_test_file.txt"
#     local_file_path = "dummy_test_file.txt"
#     download_path = "downloaded_dummy_test_file.txt"

#     s3 = get_s3_client()
#     if s3:
#         print(f"Attempting to upload to bucket: {test_bucket}")
#         if upload_file_to_s3(local_file_path, test_bucket, test_object_name, s3_client=s3):
#             print(f"Upload of {test_object_name} successful.")
            
#             url = generate_presigned_url(test_bucket, test_object_name, s3_client=s3)
#             if url:
#                 print(f"Presigned URL: {url}")
            
#             if download_file_from_s3(test_bucket, test_object_name, download_path, s3_client=s3):
#                 print(f"Download of {test_object_name} to {download_path} successful.")
#             else:
#                 print(f"Download failed.")
#         else:
#             print(f"Upload failed.")
        
#         # Clean up dummy file
#         import os
#         os.remove(local_file_path)
#         if os.path.exists(download_path):
#             os.remove(download_path)
#     else:
#         print("Could not initialize S3 client.")
