from fastapi import APIRouter, HTTPException
from src.functions import student_functions, tutor_functions
from src.models.student_model import Student, StudentUpdate, StudentPatch
import logging


router = APIRouter(prefix="/students", tags=["Students"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=list[Student])
def get_students():
    """Get all students."""
    students = student_functions.get_all_students()
    logger.info(f"Retrieved {len(students)} students.")
    return students


@router.get("/{student_name}", response_model=Student)
def get_student_by_name(student_name: str):
    """Get a specific student by name."""
    student = student_functions.get_student(student_name)
    if student:
        logger.info(f"Retrieved information for {student_name}")
    else:
        logger.error(f"Could not retrieve information for {student_name}")
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.get("/tutor/{tutor}", response_model=list[Student])
def get_students_by_tutor(tutor: str):
    """Get all students for a specific tutor (by tutor_id or name like 'mustafa')."""
    found = tutor_functions.resolve_tutor(tutor)
    if found:
        logger.info(f"Retrieving list of all students for tutor: {tutor}")
    else:
        logger.error(f"Could not retrieve list of students - tutor not found: {tutor}")
        raise HTTPException(status_code=404, detail="Tutor not found")
    return student_functions.get_students_by_tutor(found.tutor_id)


@router.put("/{student_name}", response_model=Student)
def update_student(student_name: str, updates: StudentUpdate):
    """Update a student (all fields)."""
    student = student_functions.update_student(student_name, updates)
    if student:
        logger.info(f"{student_name} information was updated.")
    else:
        logger.error(f"{student_name} information could not be updated.")
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.patch("/{student_name}", response_model=Student)
def patch_student(student_name: str, patch: StudentPatch):
    """Patch a student (only post-initialization fields by default) or specific fields."""
    student = student_functions.patch_student(student_name, patch)
    if student:
        logger.info(f"{student_name} information was patched.")
    else:
        logger.error(f"{student_name} information could not be patched.")
        raise HTTPException(status_code=404, detail="Student not found")
    return student
