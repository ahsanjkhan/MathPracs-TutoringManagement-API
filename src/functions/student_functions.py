from datetime import datetime
from typing import Optional
from src.config import get_settings
from src.functions import dynamodb, session_functions
from src.functions.google_docs import extract_student_name
from src.models.student_v2_model import StudentV2, StudentMetadataV2, StudentV2Update, StudentMetadataV2Update

settings = get_settings()


def normalize_student_name(name: str) -> str:
    """Normalize student name to title case for consistent lookups."""
    return name.strip().title()


def get_all_students() -> list[StudentV2]:
    """Get all students from StudentsV2."""
    items = dynamodb.scan_table(settings.students_table)
    return [StudentV2.from_dynamodb(item) for item in items]


def get_students_by_tutor(tutor_id: str) -> list[StudentV2]:
    """Get all students associated with a specific tutor via their sessions."""
    sessions = session_functions.get_sessions_by_tutor(tutor_id)
    student_names = set()
    for s in sessions:
        name = extract_student_name(s.summary)
        if name:
            student_names.add(normalize_student_name(name))

    students = []
    for name in student_names:
        student = get_student(name)
        if student:
            students.append(student)
    return students


def get_student(student_name: str) -> Optional[StudentV2]:
    """Get a student by name (case-insensitive). Returns None if not found."""
    normalized_name = normalize_student_name(student_name)
    item = dynamodb.get_item(settings.students_table, {"studentName": normalized_name})
    if item:
        return StudentV2.from_dynamodb(item)
    return None


def get_student_metadata(student_name: str) -> Optional[StudentMetadataV2]:
    """Get student metadata by name. Returns None if not found."""
    normalized_name = normalize_student_name(student_name)
    item = dynamodb.get_item(settings.students_metadata_table, {"studentName": normalized_name})
    if item:
        return StudentMetadataV2.from_dynamodb(item)
    return None


def update_student(student_name: str, updates: StudentV2Update) -> Optional[StudentV2]:
    """Update operational student fields in StudentsV2."""
    normalized_name = normalize_student_name(student_name)
    existing = get_student(normalized_name)
    if not existing:
        return None

    update_data = {}
    if updates.doc_url is not None:
        update_data["docUrl"] = updates.doc_url
    if updates.file_request_link is not None:
        update_data["fileRequestLink"] = updates.file_request_link
    if updates.google_meets_link is not None:
        update_data["googleMeetsLink"] = updates.google_meets_link
    if updates.hw_upload_link is not None:
        update_data["hwUploadLink"] = updates.hw_upload_link

    if not update_data:
        return existing

    updated_item = dynamodb.update_item(
        settings.students_table,
        {"studentName": normalized_name},
        update_data,
    )
    return StudentV2.from_dynamodb(updated_item)


def update_student_metadata(student_name: str, updates: StudentMetadataV2Update) -> Optional[StudentMetadataV2]:
    """Update student metadata fields in StudentsMetadataV2."""
    normalized_name = normalize_student_name(student_name)
    existing = get_student(normalized_name)
    if not existing:
        return None

    update_data = {}
    if updates.hourly_pricing is not None:
        update_data["hourlyPricing"] = updates.hourly_pricing
    if updates.phone_numbers is not None:
        update_data["phoneNumbers"] = updates.phone_numbers
    if updates.student_timezone is not None:
        update_data["studentTimezone"] = updates.student_timezone
    if updates.no_show_custom_rate is not None:
        update_data["noShowCustomRate"] = updates.no_show_custom_rate
    if updates.payment_collected_by is not None:
        update_data["paymentCollectedBy"] = updates.payment_collected_by.value

    if not update_data:
        return get_student_metadata(normalized_name)

    update_data["updatedAt"] = datetime.utcnow().isoformat()
    updated_item = dynamodb.update_item(
        settings.students_metadata_table,
        {"studentName": normalized_name},
        update_data,
    )
    return StudentMetadataV2.from_dynamodb(updated_item)
