<p align="center">
  <img src="./mathpracs-logo.png" alt="MathPracs Logo" width="350"/>
</p>
<h1 align="center">MathPracs Tutoring API</h1>


A serverless API for managing tutoring sessions, built with FastAPI and designed to run on AWS Lambda.

## Overview

This API automatically syncs with Google Calendar to track tutoring sessions and manages student records. When a new student is detected, it automatically creates:
- A Google Doc for session notes
- A Google Meet link
- A Dropbox folder for homework uploads
- Discord channels for the tutor (tutor, dropbox notifications, feedback, session reminders)

## Features

- **Google Calendar Integration** - Auto-discovers tutors and syncs sessions
- **Student Management** - Auto-creates docs, Meet links, and Dropbox folders
- **Discord Slash Commands** - Serverless bot via HTTP interactions (no EC2 needed)
- **Dropbox Webhooks** - Notifies tutors via Discord when students upload homework
- **Session Feedback** - AI-powered feedback summaries via Groq
- **AWS Lambda Ready** - Runs serverless via Mangum adapter
- **EventBridge Polling** - Syncs every 3 minutes automatically

## Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI |
| Database | DynamoDB |
| Cloud | AWS Lambda + API Gateway |
| Scheduler | AWS EventBridge |
| Storage | Google Drive, Dropbox |
| Discord | HTTP Interactions (serverless) |
| AI | Groq (feedback summaries) |

## Project Structure

```
src/
├── main.py                 # FastAPI app entry point + Lambda handler
├── config.py               # Settings and configuration
├── APIs/
│   ├── discord_api.py      # Discord interactions endpoint
│   └── dropbox_webhook_api.py  # Dropbox webhook endpoint
├── functions/
│   ├── tutor_functions.py  # Tutor business logic
│   ├── session_functions.py# Session business logic
│   ├── student_functions.py# Student business logic
│   ├── sync_functions.py   # Calendar/event sync logic
│   ├── discord_commands.py # Discord slash command handlers
│   ├── discord_utils.py    # Discord API utilities
│   ├── groq_utils.py       # AI feedback summaries
│   ├── google_calendar.py  # Google Calendar API
│   ├── google_docs.py      # Google Drive/Docs API
│   ├── google_meet.py      # Google Meet API
│   ├── dropbox.py          # Dropbox API
│   ├── dynamodb.py         # DynamoDB operations
│   ├── ssm_utils.py        # SSM Parameter Store utilities
│   ├── utils.py            # General utilities
│   └── webhook_handlers.py # Webhook processing
├── models/
│   ├── tutor_v2_model.py       # Tutor data models
│   ├── session_model.py        # Session data models
│   ├── student_v2_model.py     # Student data models
│   └── calendar_state_model.py # Sync state model
└── scripts/
    └── register_discord_commands.py  # Discord command registration
```

## API Endpoints

### Discord (Signature Verified)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/discord/interactions` | Discord slash commands, buttons & modals |

### Dropbox (Signature Verified)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/dropbox/webhook` | Dropbox webhook verification (challenge) |
| POST | `/dropbox/webhook` | Dropbox file change notifications |

### Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |

## Discord Slash Commands

The bot runs serverlessly via HTTP interactions — no EC2 or persistent connection needed.

### Tutor Commands
| Command | Description |
|---------|-------------|
| `/sessions` | View scheduled sessions for next 24 hours |
| `/links_student <name>` | Get meeting, homework folder, and upload links for a student |
| `/refresh_commands` | Update pinned onboarding message |

### Admin Commands
| Command | Description |
|---------|-------------|
| `/ping_bot` | Test if bot is connected |
| `/active_tutors` | List all active tutors |
| `/manual_sync` | Trigger calendar + event sync |
| `/get_tutor <name>` | View tutor details |
| `/get_student <name>` | View student details |
| `/update_tutor <name>` | Update tutor via modal |
| `/update_student <name>` | Update student via modal |
| `/tutor_monthly_payments` | View total earnings across all tutors for the current month |
| `/hours_tutored_chart` | Bar chart of total hours tutored per month |
| `/help` | Show all commands and descriptions |

### Session Feedback
When a session is completed, tutors receive a feedback prompt with a button in their feedback channel. Clicking it opens a modal to enter feedback, which is then summarized by AI (Groq) and posted to a feedback channel.

## Setup

### Prerequisites

- Python 3.11+
- AWS Account with infrastructure deployed via [MathPracs-TutoringManagement-CDK](https://github.com/ahsanjkhan/MathPracs-TutoringManagement-CDK)

### 1. Install Dependencies

```bash
# For Lambda deployment
pip install -r requirements.txt

# For local development (includes uvicorn)
pip install -r requirements-local.txt
```

### 2. AWS Secrets Manager

Secrets are created by the CDK stack. Update them with your API credentials:

**Google Credentials** (`tutoring-api/google-credentials-cdk`):
```json
{
  "type": "service_account",
  "project_id": "...",
  "private_key": "...",
  "client_email": "...",
  "oauth_web_client_id": "...",
  "oauth_web_client_secret": "...",
  "allowed_emails": ["<email>"]
}
```

**Dropbox Credentials** (`tutoring-api/dropbox-credentials-cdk`):
```json
{
  "app_key": "...",
  "app_secret": "...",
  "refresh_token": "..."
}
```

**Discord Credentials** (`tutoring-api/discord-credentials-cdk`):
```json
{
  "bot_token": "...",
  "application_id": "...",
  "public_key": "...",
  "guild_id": "...",
  "bot_id": "...",
  "session_feedback_channel_id": "...",
  "muaz_student_payment_channel_id": "...",
  "ahsan_student_payment_channel_id": "..."
}
```

**Groq Credentials** (`tutoring-api/groq-credentials-cdk`):
```json
{
  "api_key": "..."
}
```

### 3. DynamoDB Tables

Tables are created by the CDK stack:

| Table | Partition Key | Sort Key |
|-------|---------------|----------|
| TutorsV2 | tutorId (S) | - |
| TutorsMetadataV2 | tutorId (S) | - |
| Sessions | tutorId (S) | sessionId (S) |
| StudentsV2 | studentName (S) | - |
| StudentsMetadataV2 | studentName (S) | - |
| Transactions | studentName (S) | transactionKey (S) |
| CalendarListState | syncType (S) | - |

### 4. Run Locally

```bash
uvicorn src.main:app --reload
```

### 5. Deploy to AWS Lambda

Raising a Pull Request for commits on a feature branch, getting it approved, and squashing and merging into `main` on either this repo or [MathPracs-TutoringManagement-CDK](https://github.com/ahsanjkhan/MathPracs-TutoringManagement-CDK) automatically triggers the CodePipeline, which runs deploys the changes.

#### Manual Deployments (Avoid if possible)
1. Make changes on feature branch.
2. Commit those changes and raise Pull Request as usual.
3. Deploy the changes directly from MathPracs-TutoringManagement-CDK:
   ```bash
   CDK_DOCKER=finch npx cdk deploy MathPracsTutoringManagementCdkStack
   ```


### 6. Register Discord Slash Commands

```bash
python -m src.scripts.register_discord_commands
```

Then in Discord Developer Portal, set **Interactions Endpoint URL** to:
```
https://your-api-gateway-url/prod/discord/interactions
```

## Configuration

Environment variables (prefix with `TUTORING_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | us-east-1 | AWS region |
| `TUTORS_TABLE` | TutorsV2 | Tutors DynamoDB table |
| `TUTORS_METADATA_TABLE` | TutorsMetadataV2 | Tutors metadata table |
| `SESSIONS_TABLE` | Sessions | Sessions DynamoDB table |
| `STUDENTS_TABLE` | StudentsV2 | Students DynamoDB table |
| `STUDENTS_METADATA_TABLE` | StudentsMetadataV2 | Students metadata table |
| `TRANSACTIONS_TABLE` | Transactions | Transactions DynamoDB table |
| `CALENDAR_SYNC_TABLE` | CalendarListState | Calendar sync state table |
| `GOOGLE_CREDENTIALS_SECRET_NAME` | tutoring-api/google-credentials-cdk | Google credentials secret |
| `DROPBOX_CREDENTIALS_SECRET_NAME` | tutoring-api/dropbox-credentials-cdk | Dropbox credentials secret |
| `DISCORD_CREDENTIALS_SECRET_NAME` | tutoring-api/discord-credentials-cdk | Discord credentials secret |
| `GROQ_CREDENTIALS_SECRET_NAME` | tutoring-api/groq-credentials-cdk | Groq credentials secret |
| `PARENT_DRIVE_FOLDER_ID_SSM_NAME` | /tutoring-api/parent-drive-folder-id | Google Drive parent folder SSM param |
| `DROPBOX_PARENT_FOLDER_SSM_NAME` | /tutoring-api/dropbox-parent-folder | Dropbox parent folder SSM param |

## How It Works

### Lambda Handler

The Lambda handler in `main.py` routes three types of events:
1. **Discord async tasks** — fire-and-forget Lambda self-invocations for slow commands
2. **EventBridge scheduled events** — triggers calendar + session sync directly (not via API routes)
3. **API Gateway requests** — handled by FastAPI via Mangum

### Sync Flow

1. **EventBridge** triggers sync every 3 minutes
2. **Calendar Sync** discovers tutors from calendars with "tutoring" in the name
3. **Event Sync** fetches events with "tutoring" keyword
4. **Student Detection** extracts student name from event title (e.g., "Ved Tutoring" → Ved)
5. **Auto-Setup** creates Google Doc, Meet link, Dropbox folder, and Discord channels for new students/tutors
6. **Doc Attachment** attaches the MathPracs doc to calendar events
7. **Feedback Prompt** sends a feedback button to the tutor's feedback channel when a session completes

### Naming Convention

- Calendar events: `{StudentName} Tutoring` (e.g., "Ved Tutoring")
- Google Docs: `{StudentName} MathPracs` (e.g., "Ved MathPracs")
- Dropbox folders: `{StudentName} MathPracs`
- Discord channels: `tutor-{name}`, `dropbox-{name}`, `feedback-{name}`, `session-reminders-{name}`

## Session Statuses

| Status | Description |
|--------|-------------|
| `scheduled` | Upcoming session |
| `completed` | Past session (auto-set based on end time) |

## Tutor Statuses

| Status | Description |
|--------|-------------|
| `active` | Currently tracked |
| `inactive` | Deactivated/removed |
