import logging
import json
import boto3
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2AuthorizationCodeBearer
from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Load OAuth config from Secrets Manager
_auth_config = None


def get_auth_config():
    """Get or create cached OAuth config from Secrets Manager."""
    global _auth_config
    if _auth_config is None:
        secrets_client = boto3.client("secretsmanager", region_name=settings.aws_region)
        response = secrets_client.get_secret_value(SecretId=settings.google_credentials_secret_name)
        creds = json.loads(response["SecretString"])
        _auth_config = {
            "oauth_web_client_id": creds.get("oauth_web_client_id", ""),
            "oauth_web_client_secret": creds.get("oauth_web_client_secret", ""),
            "allowed_emails": creds.get("allowed_emails", []),
        }
    return _auth_config


# OAuth2 scheme for Swagger UI
oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl="https://accounts.google.com/o/oauth2/v2/auth",
    tokenUrl="https://oauth2.googleapis.com/token",
    scopes={
        "openid": "OpenID Connect",
        "email": "Email address",
        "profile": "Profile info",
    },
)


def verify_google_token(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Verify Google OAuth2 access token by calling Google's userinfo endpoint.
    Returns user info if valid.
    """
    auth_config = get_auth_config()

    try:
        # Use the access token to get user info from Google
        response = httpx.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token}"}
        )

        if response.status_code != 200:
            logger.warning(f"Google userinfo request failed: {response.status_code}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_info = response.json()
        email = user_info.get("email", "")

        # Check if email is in allowed list
        allowed_emails = auth_config["allowed_emails"]
        if allowed_emails and email not in allowed_emails:
            logger.warning(f"Unauthorized email attempted access: {email}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Email {email} is not authorized to access this API"
            )

        logger.info(f"Authenticated user: {email}")
        return {
            "email": email,
            "name": user_info.get("name"),
            "picture": user_info.get("picture"),
        }

    except httpx.RequestError as e:
        logger.warning(f"Failed to verify token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to verify token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Dependency to use in routes
def get_current_user(user: dict = Depends(verify_google_token)) -> dict:
    """FastAPI dependency that returns the authenticated user's info."""
    return user
