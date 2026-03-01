import logging
import sys
from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager
from mangum import Mangum
from src.APIs import sync_api, discord_api, dropbox_webhook_api
from src.auth import get_current_user, get_auth_config
from src.functions import sync_functions, discord_commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

logging.getLogger("dropbox").setLevel(logging.WARNING)
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.WARNING)


_DISCORD_TASK_HANDLERS = {
    "sessions":             discord_commands.handle_sessions,
    "earnings":             discord_commands.handle_earnings,
    "links_student":        discord_commands.handle_links_student,
    "tutor_monthly_payments": discord_commands.handle_total_earnings,
    "hours_tutored_chart":  discord_commands.handle_hours_tutored_chart,
}


def lambda_handler(event, context):
    """Handle API Gateway, EventBridge, and async Discord task events."""
    # Async Discord task (fire-and-forget from the interactions handler)
    if "discord_task" in event:
        task = event["discord_task"]
        command = task.get("command")
        handler_fn = _DISCORD_TASK_HANDLERS.get(command)
        if handler_fn:
            try:
                handler_fn(task["interaction"], task["application_id"])
            except Exception as e:
                logger.error(f"Discord task failed for '{command}': {e}")
        else:
            logger.warning(f"Unknown discord_task command: {command}")
        return {"statusCode": 200}

    # EventBridge scheduled sync
    if event.get('source') == 'aws.events' or 'detail-type' in event:
        logger.info("EventBridge sync triggered")
        try:
            # Run the sync directly
            calendar_result = sync_functions.sync_calendar_list()
            sessions_result = sync_functions.sync_events_list(tutor_cal_id="ALL")
            logger.info(f"Sync completed - calendars: {calendar_result}, sessions: {sessions_result}")
            return {
                "statusCode": 200,
                "body": {
                    "message": "Sync completed",
                    "calendars": calendar_result,
                    "sessions": sessions_result,
                }
            }
        except Exception as e:
            logger.error(f"Sync failed: {str(e)}")
            return {
                "statusCode": 500,
                "body": {"error": str(e)}
            }
    
    # Otherwise, handle as API Gateway event
    return handler(event, context)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle handler."""
    logger.info("FastAPI starting up...")
    yield
    logger.info("FastAPI shutting down...")


auth_config = get_auth_config()

app = FastAPI(
    title="Tutoring API",
    version="2.0.0",
    description="Serverless Tutoring Management API with Google Calendar Integration",
    lifespan=lifespan,
    swagger_ui_oauth2_redirect_url="/docs/oauth2-redirect",
    swagger_ui_init_oauth={
        "clientId": auth_config["oauth_web_client_id"],
        "clientSecret": auth_config["oauth_web_client_secret"],
        "scopes": "openid email profile",
        "usePkceWithAuthorizationCodeGrant": True,
    },
)


@app.get("/health")
def health_check():
    return {"status": "healthy"}


#Public routes (no auth - for EventBridge, health checks, Discord, and webhooks)
app.include_router(sync_api.router)
app.include_router(discord_api.router)
app.include_router(dropbox_webhook_api.router)

handler = Mangum(app, lifespan="auto")
