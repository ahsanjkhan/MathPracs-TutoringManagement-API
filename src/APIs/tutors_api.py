from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.models.tutor_v2_model import TutorV2, TutorStatus, TutorV2Update, TutorMetadataV2Update
from src.functions import tutor_functions
import logging

router = APIRouter(prefix="/tutors", tags=["Tutors"])
logger = logging.getLogger(__name__)


class TutorPatchRequest(BaseModel):
    """Combined patch body — fields are routed to TutorsV2 or TutorsMetadataV2 as appropriate."""
    display_name: Optional[str] = None
    status: Optional[TutorStatus] = None
    hourly_rate: Optional[float] = None
    tutor_email: Optional[str] = None
    tutor_phone: Optional[str] = None
    tutor_timezone: Optional[str] = None


@router.get("", response_model=list[TutorV2])
def get_tutors(status: Optional[TutorStatus] = None):
    """Get all tutors."""
    tutors = tutor_functions.get_all_tutors(status_filter=status)
    logger.info(f"Retrieved {len(tutors)} tutors.")
    return tutors


@router.get("/{tutor}", response_model=TutorV2)
def get_tutor_by_id(tutor: str):
    """Get tutor by tutor_id or name (e.g. 'mustafa')."""
    found = tutor_functions.resolve_tutor(tutor)
    if not found:
        logger.error(f"Tutor: {tutor} not found.")
        raise HTTPException(status_code=404, detail="Tutor not found")
    logger.info(f"Retrieved tutor: {tutor}.")
    return found


@router.patch("/{tutor}", response_model=TutorV2)
def patch_tutor(tutor: str, updates: TutorPatchRequest):
    """Patch tutor by tutor_id or name. Operational fields go to TutorsV2, metadata fields to TutorsMetadataV2."""
    found = tutor_functions.resolve_tutor(tutor)
    if not found:
        raise HTTPException(status_code=404, detail="Tutor not found")

    tutor_functions.update_tutor(
        found.tutor_id,
        TutorV2Update(display_name=updates.display_name, status=updates.status),
    )
    tutor_functions.update_tutor_metadata(
        found.tutor_id,
        TutorMetadataV2Update(
            hourly_rate=updates.hourly_rate,
            tutor_email=updates.tutor_email,
            tutor_phone=updates.tutor_phone,
            tutor_timezone=updates.tutor_timezone,
        ),
    )

    result = tutor_functions.get_tutor(found.tutor_id)
    if result:
        logger.info(f"Tutor: {tutor} patched.")
        return result
    raise HTTPException(status_code=500, detail="Failed to patch tutor")


@router.delete("/{tutor}")
def delete_tutor(tutor: str):
    """Deactivate tutor by tutor_id or name."""
    found = tutor_functions.resolve_tutor(tutor)
    if not found:
        raise HTTPException(status_code=404, detail="Tutor not found")
    deleted = tutor_functions.delete_tutor(found.tutor_id)
    if deleted:
        logger.info(f"Tutor: {tutor} deactivated.")
        return {"message": "Tutor deactivated"}
    raise HTTPException(status_code=500, detail="Failed to deactivate tutor")
