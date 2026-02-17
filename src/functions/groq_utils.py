import json
import logging
import boto3
import httpx
from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_groq_credentials = None


def get_groq_credentials() -> dict:
    """Get Groq API key from AWS Secrets Manager."""
    global _groq_credentials
    if _groq_credentials is None:
        secrets_client = boto3.client("secretsmanager", region_name=settings.aws_region)
        response = secrets_client.get_secret_value(SecretId=settings.groq_credentials_secret_name)
        _groq_credentials = json.loads(response["SecretString"])
    return _groq_credentials


def generate_feedback_summary(raw_feedback: str, student_name: str) -> str | None:
    """
    Use Groq API to convert raw feedback into a professional 2-3 sentence summary.
    Returns the summary or None if failed.
    """
    creds = get_groq_credentials()
    api_key = creds.get("api_key")

    if not api_key:
        logger.error("Groq API key not configured")
        return None

    prompt = f"""Convert this tutoring session note into a professional 2-3 sentence summary for parents.
Keep it positive, constructive, and focus on what the student worked on and their progress.
Student name: {student_name}

Tutor's note: "{raw_feedback}"

Write the summary in third person, referring to the student by name."""

    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that writes professional tutoring session summaries for parents."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 200,
                "temperature": 0.7
            },
            timeout=30.0
        )

        if response.status_code == 200:
            data = response.json()
            summary = data["choices"][0]["message"]["content"].strip()
            logger.info(f"Generated feedback summary for {student_name}")
            return summary
        else:
            logger.error(f"Groq API error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error calling Groq API: {e}")
        return None
