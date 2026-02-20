import boto3
from functools import lru_cache
from src.config import get_settings

settings = get_settings()

@lru_cache(maxsize=128)
def get_ssm_parameter(parameter_name: str) -> str:
    """Get SSM parameter value with caching."""
    ssm = boto3.client('ssm', region_name=settings.aws_region)
    response = ssm.get_parameter(Name=parameter_name)
    return response['Parameter']['Value']

def get_parent_drive_folder_id() -> str:
    """Get the parent drive folder ID from SSM."""
    return get_ssm_parameter(settings.parent_drive_folder_id_ssm_name)

def get_dropbox_parent_folder() -> str:
    """Get the dropbox parent folder path from SSM."""
    return get_ssm_parameter(settings.dropbox_parent_folder_ssm_name)