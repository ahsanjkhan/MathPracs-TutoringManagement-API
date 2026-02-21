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

## Features

- **Google Calendar Integration** - Auto-discovers tutors and syncs sessions
- **Student Management** - Auto-creates docs, Meet links, and Dropbox folders
- **Discord Slash Commands** - Serverless bot via HTTP interactions (no EC2 needed)
- **Session Feedback** - AI-powered feedback summaries via Groq
- **Google OAuth2** - Protected API routes with email allowlist
- **AWS Lambda Ready** - Runs serverless via Mangum adapter
- **EventBridge Polling** - Syncs every 3 minutes automatically

## Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI |
| Database | DynamoDB |
| Auth | Google OAuth2 |
| Cloud | AWS Lambda + API Gateway |
| Scheduler | AWS EventBridge |
| Storage | Google Drive, Dropbox |
| Discord | HTTP Interactions (serverless) |
| AI | Groq (feedback summaries) |

## Project Structure

```
src/
├── main.py                 # FastAPI app entry point
├── auth.py                 # Google OAuth2 authentication
├── config.py               # Settings and configuration
├── APIs/
│   ├── tutors_api.py       # Tutor endpoints
│   ├── sessions_api.py     # Session endpoints
│   ├── students_api.py     # Student endpoints
│   ├── sync_api.py         # Sync endpoints (EventBridge)
│   └── discord_api.py      # Discord interactions endpoint
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
│   └── dynamodb.py         # DynamoDB operations
└── models/
    ├── tutor_model.py      # Tutor data models
    ├── session_model.py    # Session data models
    ├── student_model.py    # Student data models
    └── calendar_state_model.py # Sync state model

scripts/
└── register_commands.py    # One-time Discord command registration
```

## API Endpoints

### Tutors
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tutors` | Get all tutors |
| GET | `/tutors/{tutor}` | Get tutor by ID or name |
| PATCH | `/tutors/{tutor}` | Update tutor |
| DELETE | `/tutors/{tutor}` | Deactivate tutor |

### Sessions
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sessions` | Get all sessions |
| POST | `/sessions` | Create session |
| GET | `/sessions/tutor/{tutor}` | Get sessions by tutor |
| PATCH | `/sessions/tutor/{tutor}/{session_id}` | Update session |
| DELETE | `/sessions/tutor/{tutor}/{session_id}` | Delete session |

### Students
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/students` | Get all students |
| GET | `/students/{student_name}` | Get student by name |
| GET | `/students/tutor/{tutor}` | Get students by tutor |
| PUT | `/students/{student_name}` | Update student |
| PATCH | `/students/{student_name}` | Patch student |

### Sync (Public - No Auth)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/sync/calendars` | Sync calendars only |
| POST | `/sync/sessions` | Full sync (calendars + sessions) |

### Discord (Public - Signature Verified)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/discord/interactions` | Discord slash commands & buttons |

## Discord Slash Commands

The bot runs serverlessly via HTTP interactions - no EC2 or persistent connection needed.

### Tutor Commands
| Command | Description |
|---------|-------------|
| `/ping_bot` | Test if bot is connected |
| `/sessions` | View scheduled sessions for next 24 hours |
| `/refresh_commands` | Update pinned onboarding message |

### Admin Commands
| Command | Description |
|---------|-------------|
| `/manual_sync` | Trigger calendar + event sync |
| `/active_tutors` | List all active tutors |
| `/get_tutor <name>` | View tutor details |
| `/get_student <name>` | View student details |
| `/update_tutor <name>` | Update tutor via modal |
| `/update_student <name>` | Update student via modal |

### Session Feedback
When a session is completed, tutors receive a feedback prompt with a button. Clicking it opens a modal to enter feedback, which is then summarized by AI (Groq) and posted to a feedback channel.

## Setup

### Prerequisites

- Python 3.10+
- AWS Account with DynamoDB tables
- Google Cloud Project with APIs enabled
- Dropbox App

### 1. Install Dependencies

```bash
# For Lambda deployment
pip install -r requirements.txt

# For local development (includes uvicorn)
pip install -r requirements-local.txt
```

### 2. AWS Secrets Manager

Store credentials in AWS Secrets Manager:

**Google Credentials** (`tutoring-api/google-credentials`):
```json
{
  "type": "service_account",
  "project_id": "...",
  "private_key": "...",
  "client_email": "...",
  "oauth_web_client_id": "...",
  "oauth_web_client_secret": "...",
  "allowed_emails": ["user@example.com"]
}
```

**Dropbox Credentials** (`tutoring-api/dropbox-credentials`):
```json
{
  "app_key": "...",
  "app_secret": "...",
  "refresh_token": "..."
}
```

**Discord Credentials** (`tutoring-api/discord-credentials`):
```json
{
  "bot_token": "...",
  "application_id": "...",
  "public_key": "...",
  "guild_id": "...",
  "bot_id": "...",
  "session_feedback_channel_id": "..."
}
```

**Groq Credentials** (`tutoring-api/groq-credentials`):
```json
{
  "api_key": "..."
}
```

### 3. DynamoDB Tables

Create the following tables:

| Table | Partition Key | Sort Key |
|-------|---------------|----------|
| Tutors | tutorId (S) | - |
| Sessions | tutorId (S) | sessionId (S) |
| Students | studentName (S) | - |
| CalendarListState | syncType (S) | - |

### 4. Run Locally

```bash
uvicorn src.main:app --reload
```

Access Swagger UI at: `http://localhost:8000/docs`

### 5. Deploy to AWS Lambda

The app uses Mangum for Lambda compatibility. Deploy using your preferred method (SAM, Serverless Framework, CDK, etc.).

### 6. Setup Discord Slash Commands

1. Register commands with Discord:
```bash
python scripts/register_commands.py --guild
```

2. In Discord Developer Portal, set **Interactions Endpoint URL** to:
```
https://your-api-gateway-url/prod/discord/interactions
```

Discord will verify the endpoint before saving.

## Configuration

Environment variables (prefix with `TUTORING_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | us-east-1 | AWS region |
| `TUTORS_TABLE` | Tutors | DynamoDB table name |
| `SESSIONS_TABLE` | Sessions | DynamoDB table name |
| `STUDENTS_TABLE` | Students | DynamoDB table name |
| `CALENDAR_SYNC_TABLE` | CalendarListState | DynamoDB table name |

## How It Works

### Sync Flow

1. **EventBridge** triggers `/sync/sessions` every 3 minutes
2. **Calendar Sync** discovers tutors from calendars with "tutoring" in the name
3. **Event Sync** fetches events with "tutoring" keyword
4. **Student Detection** extracts student name from event title (e.g., "Ved Tutoring" → Ved)
5. **Auto-Setup** creates Google Doc, Meet link, and Dropbox folder for new students
6. **Doc Attachment** attaches the MathPracs doc to calendar events

### Naming Convention

- Calendar events: `{StudentName} Tutoring` (e.g., "Ved Tutoring")
- Google Docs: `{StudentName} MathPracs` (e.g., "Ved MathPracs")
- Dropbox folders: `{StudentName} MathPracs`

### Authentication

- **Protected routes**: Tutors, Sessions, Students (require Google OAuth)
- **Public routes**: Sync endpoints (for EventBridge), Health check

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
