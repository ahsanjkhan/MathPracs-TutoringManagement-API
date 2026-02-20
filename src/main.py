import logging
import sys
from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager
from mangum import Mangum
from src.APIs import tutors_api, sessions_api, sync_api, students_api
from src.auth import get_current_user, get_auth_config
from src.functions import sync_functions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

logging.getLogger("dropbox").setLevel(logging.WARNING)
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.WARNING)


def lambda_handler(event, context):
    """Handle both API Gateway and EventBridge events."""
    # Check if this is an EventBridge event
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


#Protected routes (require Google OAuth)
app.include_router(tutors_api.router, dependencies=[Depends(get_current_user)])
app.include_router(sessions_api.router, dependencies=[Depends(get_current_user)])
app.include_router(students_api.router, dependencies=[Depends(get_current_user)])

#Public routes (no auth - for EventBridge and health checks)
app.include_router(sync_api.router)

handler = Mangum(app, lifespan="auto")
