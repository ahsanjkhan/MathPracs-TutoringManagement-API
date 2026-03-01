from typing import Optional
from fastapi import APIRouter, HTTPException
from src.models.session_model import SessionStatus, SessionCreate, SessionUpdate, SessionResponse
from src.functions import session_functions, tutor_functions
import logging

router = APIRouter(prefix="/sessions", tags=["Sessions"])

logger = logging.getLogger(__name__)


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(session_data: SessionCreate):
    """Create a new session. Sessions before Jan 1, 2026 are not allowed."""
    session = session_functions.create_session(session_data)
    if not session:
        raise HTTPException(
            status_code=400,
            detail="Cannot create session before January 1, 2026",
        )
    logger.info("Session Created")
    return SessionResponse(**session.model_dump())


@router.get("", response_model=list[SessionResponse])
def get_sessions(status: Optional[SessionStatus] = None):
    """Get all sessions, optionally filtered by status."""
    sessions = session_functions.get_all_sessions(status_filter=status)
    logger.info(f"Retrieved {len(sessions)} sessions.")
    return [SessionResponse(**s.model_dump()) for s in sessions]


@router.get("/tutor/{tutor}", response_model=list[SessionResponse])
def get_sessions_by_tutor(tutor: str, status: Optional[SessionStatus] = None):
    """Get all sessions for a specific tutor (by tutor_id or name like 'mustafa')."""
    found = tutor_functions.resolve_tutor(tutor)
    if not found:
        raise HTTPException(status_code=404, detail="Tutor not found")
    sessions = session_functions.get_sessions_by_tutor(found.tutor_id, status_filter=status)
    logger.info(f"Sessions Retrieved for {found.display_name}")
    return [SessionResponse(**s.model_dump()) for s in sessions]


@router.patch("/tutor/{tutor}/{session_id}", response_model=SessionResponse)
def patch_session(tutor: str, session_id: str, updates: SessionUpdate):
    """Patches/Updates the session (by tutor_id or name like 'mustafa')."""
    found = tutor_functions.resolve_tutor(tutor)
    if not found:
        raise HTTPException(status_code=404, detail="Tutor not found")
    session = session_functions.patch_session(found.tutor_id, session_id, updates)
    if session:
        logger.info(f"Session {session_id} has been patched.")
    else:
        logger.error(f"Session {session_id} could not be patched.")
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(**session.model_dump())


@router.delete("/tutor/{tutor}/{session_id}")
def delete_session(tutor: str, session_id: str):
    """Delete a session (by providing session_id and tutor_id or tutor name)."""
    found = tutor_functions.resolve_tutor(tutor)
    if not found:
        raise HTTPException(status_code=404, detail="Tutor not found")
    success = session_functions.delete_session(found.tutor_id, session_id)
    if success:
        logger.info(f"Session with id:{session_id} has been deleted!")
    else:
        logger.error(f"Session with id:{session_id} could not be deleted!")
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}
