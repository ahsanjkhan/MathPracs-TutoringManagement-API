from datetime import datetime, timezone

# Case-insensitive match for "tutoring" keyword in calendar events
SESSION_KEYWORD = r"\btutoring\b"

# Only sync sessions on or after this date
SESSION_CUTOFF_DATE = datetime(2026, 1, 1, tzinfo=timezone.utc)

# How many days ahead to sync sessions
SESSION_LOOKAHEAD_DAYS = 7
