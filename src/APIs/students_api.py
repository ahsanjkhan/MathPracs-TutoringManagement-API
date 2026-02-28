from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from src.functions import student_functions, tutor_functions
from src.models.student_v2_model import StudentV2, StudentV2Update, StudentMetadataV2Update, PaymentCollector
import logging


router = APIRouter(prefix="/students", tags=["Students"])
logger = logging.getLogger(__name__)


class StudentPatchRequest(BaseModel):
    """Combined patch body — fields are routed to StudentsV2 or StudentsMetadataV2 as appropriate."""
    doc_url: Optional[str] = None
    file_request_link: Optional[str] = None
    google_meets_link: Optional[str] = None
    hw_upload_link: Optional[str] = None
    hourly_pricing: Optional[dict] = None
    phone_numbers: Optional[dict] = None
    student_timezone: Optional[str] = None
    no_show_custom_rate: Optional[float] = None
    payment_collected_by: Optional[PaymentCollector] = None


@router.get("/", response_model=list[StudentV2])
def get_students():
    """Get all students."""
    students = student_functions.get_all_students()
    logger.info(f"Retrieved {len(students)} students.")
    return students


@router.get("/{student_name}", response_model=StudentV2)
def get_student_by_name(student_name: str):
    """Get a specific student by name."""
    student = student_functions.get_student(student_name)
    if not student:
        logger.error(f"Student not found: {student_name}")
        raise HTTPException(status_code=404, detail="Student not found")
    logger.info(f"Retrieved student: {student_name}")
    return student


@router.get("/tutor/{tutor}", response_model=list[StudentV2])
def get_students_by_tutor(tutor: str):
    """Get all students for a specific tutor (by tutor_id or name)."""
    found = tutor_functions.resolve_tutor(tutor)
    if not found:
        logger.error(f"Tutor not found: {tutor}")
        raise HTTPException(status_code=404, detail="Tutor not found")
    logger.info(f"Retrieving students for tutor: {tutor}")
    return student_functions.get_students_by_tutor(found.tutor_id)


@router.patch("/{student_name}", response_model=StudentV2)
def patch_student(student_name: str, updates: StudentPatchRequest):
    """Patch a student. Operational fields go to StudentsV2, metadata fields to StudentsMetadataV2."""
    student_functions.update_student(
        student_name,
        StudentV2Update(
            doc_url=updates.doc_url,
            file_request_link=updates.file_request_link,
            google_meets_link=updates.google_meets_link,
            hw_upload_link=updates.hw_upload_link,
        ),
    )
    student_functions.update_student_metadata(
        student_name,
        StudentMetadataV2Update(
            hourly_pricing=updates.hourly_pricing,
            phone_numbers=updates.phone_numbers,
            student_timezone=updates.student_timezone,
            no_show_custom_rate=updates.no_show_custom_rate,
            payment_collected_by=updates.payment_collected_by,
        ),
    )

    result = student_functions.get_student(student_name)
    if result:
        logger.info(f"Student {student_name} patched.")
        return result
    raise HTTPException(status_code=404, detail="Student not found")
