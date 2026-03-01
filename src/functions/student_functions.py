from typing import Optional
from src.config import get_settings
from src.functions import dynamodb
from src.models.student_model import Student, StudentUpdate

settings = get_settings()


def normalize_student_name(name: str) -> str:
    """Normalize student name to title case for consistent lookups."""
    return name.strip().title()


def get_student(student_name: str) -> Optional[Student]:
    """Get a student by name (case-insensitive). Returns None if not found."""
    normalized_name = normalize_student_name(student_name)
    item = dynamodb.get_item(settings.students_table, {"studentName": normalized_name})
    if item:
        return Student.from_dynamodb(item)
    return None


def update_student(student_name: str, updates: StudentUpdate) -> Optional[Student]:
    """Updates the student record using StudentUpdate model (all fields)."""
    normalized_name = normalize_student_name(student_name)
    existing = get_student(normalized_name)
    if not existing:
        return None

    update_data = {}
    if updates.doc_url is not None:
        update_data["docUrl"] = updates.doc_url
    if updates.student_timezone is not None:
        update_data["studentTimezone"] = updates.student_timezone
    if updates.student_email is not None:
        update_data["studentEmail"] = updates.student_email
    if updates.google_meets_link is not None:
        update_data["googleMeetsLink"] = updates.google_meets_link
    if updates.hw_upload_link is not None:
        update_data["hwUploadLink"] = updates.hw_upload_link
    if updates.file_request_link is not None:
        update_data["fileRequestLink"] = updates.file_request_link
    if updates.number_1 is not None:
        update_data["number1"] = {"phoneNumber": updates.number_1.phone_number, "smsEnabled": updates.number_1.sms_enabled}
    if updates.number_2 is not None:
        update_data["number2"] = {"phoneNumber": updates.number_2.phone_number, "smsEnabled": updates.number_2.sms_enabled}
    if updates.number_3 is not None:
        update_data["number3"] = {"phoneNumber": updates.number_3.phone_number, "smsEnabled": updates.number_3.sms_enabled}
    if updates.number_4 is not None:
        update_data["number4"] = {"phoneNumber": updates.number_4.phone_number, "smsEnabled": updates.number_4.sms_enabled}
    if updates.number_5 is not None:
        update_data["number5"] = {"phoneNumber": updates.number_5.phone_number, "smsEnabled": updates.number_5.sms_enabled}
    if updates.hourly_price_standard is not None:
        update_data["hourlyPriceStandard"] = updates.hourly_price_standard
    if updates.hourly_price_1 is not None:
        update_data["hourlyPrice1"] = updates.hourly_price_1
    if updates.hourly_price_2 is not None:
        update_data["hourlyPrice2"] = updates.hourly_price_2
    if updates.hourly_price_3 is not None:
        update_data["hourlyPrice3"] = updates.hourly_price_3
    if updates.hourly_price_4 is not None:
        update_data["hourlyPrice4"] = updates.hourly_price_4
    if updates.hourly_price_5 is not None:
        update_data["hourlyPrice5"] = updates.hourly_price_5
    if updates.hourly_price_no_show is not None:
        update_data["hourlyPriceNoShow"] = updates.hourly_price_no_show
    if updates.payment_collected_by is not None:
        update_data["paymentCollectedBy"] = updates.payment_collected_by.value

    if not update_data:
        return existing

    updated_item = dynamodb.update_item(
        settings.students_table,
        {"studentName": normalized_name},
        update_data,
    )
    return Student.from_dynamodb(updated_item)



