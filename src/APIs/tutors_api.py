from typing import Optional
from fastapi import APIRouter, HTTPException
from src.models.tutor_model import TutorStatus, TutorUpdate, TutorResponse
from src.functions import tutor_functions
import logging

router = APIRouter(prefix="/tutors", tags=["Tutors"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[TutorResponse])
def get_tutors(status: Optional[TutorStatus] = None):
    """Route to get all tutors"""
    tutors = tutor_functions.get_all_tutors(status_filter=status)
    logger.info(f"Retrieved {len(tutors)} tutors.")
    return [TutorResponse(**t.model_dump()) for t in tutors]


@router.get("/{tutor}", response_model=TutorResponse)
def get_tutor_by_id(tutor: str):
    """Route to get tutor info by tutor_id or name (e.g., 'mustafa')."""
    found = tutor_functions.resolve_tutor(tutor)
    if found:
        logger.info(f"Tutor: {tutor} information was retrieved.")
    else:
        logger.error(f"Tutor: {tutor} information could not be retrieved.")
        raise HTTPException(status_code=404, detail="Tutor not found")
    return TutorResponse(**found.model_dump())


@router.patch("/{tutor}", response_model=TutorResponse)
def patch_tutor(tutor: str, updates: TutorUpdate):
    """Route to patch tutor record by tutor_id or name."""
    found = tutor_functions.resolve_tutor(tutor)
    if not found:
        raise HTTPException(status_code=404, detail="Tutor not found")
    updated = tutor_functions.update_tutor(found.tutor_id, updates)
    if updated:
        logger.info(f"Tutor: {tutor} information has been patched.")
        return TutorResponse(**updated.model_dump())
    else:
        logger.error(f"Tutor: {tutor} information could not be patched.")
        raise HTTPException(status_code=500, detail="Failed to patch tutor")


@router.delete("/{tutor}")
def delete_tutor(tutor: str):
    """Route to make tutor inactive by tutor_id or name."""
    found = tutor_functions.resolve_tutor(tutor)
    if not found:
        raise HTTPException(status_code=404, detail="Tutor not found")
    deleted = tutor_functions.delete_tutor(found.tutor_id)
    if deleted:
        logger.info(f"Tutor: {tutor} has been made inactive.")
        return {"message": "Tutor deactivated"}
    else:
        logger.error(f"Tutor: {tutor} could not be made inactive after being found successfully.")
        raise HTTPException(status_code=500, detail="Failed to deactivate tutor")
