from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class PaymentCollector(str, Enum):
    MUAZ = "muaz"
    AHSAN = "ahsan"
    BUSINESS = "business"


class PhoneNumber(BaseModel):
    phone_number: str
    sms_enabled: bool = True


class Student(BaseModel):
    student_name: str
    doc_id: str
    doc_url: Optional[str] = None
    student_timezone: Optional[str] = None
    student_email: Optional[str] = None
    google_meets_link: Optional[str] = None
    hw_upload_link: Optional[str] = None
    file_request_link: Optional[str] = None
    number_1: Optional[PhoneNumber] = None
    number_2: Optional[PhoneNumber] = None
    number_3: Optional[PhoneNumber] = None
    number_4: PhoneNumber = Field(default_factory=lambda: PhoneNumber(phone_number="18325745458", sms_enabled=True))
    number_5: PhoneNumber = Field(default_factory=lambda: PhoneNumber(phone_number="18324174712", sms_enabled=True))
    hourly_price_1: Optional[float] = None
    hourly_price_2: Optional[float] = None
    hourly_price_3: Optional[float] = None
    hourly_price_4: Optional[float] = None
    hourly_price_5: Optional[float] = None
    hourly_price_no_show: Optional[float] = None
    payment_collected_by: Optional[PaymentCollector] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_dynamodb(self) -> dict:
        data = {
            "studentName": self.student_name,
            "docId": self.doc_id,
            "number4": {"phoneNumber": self.number_4.phone_number, "smsEnabled": self.number_4.sms_enabled},
            "number5": {"phoneNumber": self.number_5.phone_number, "smsEnabled": self.number_5.sms_enabled},
            "createdAt": self.created_at.isoformat(),
        }
        if self.doc_url:
            data["docUrl"] = self.doc_url
        if self.student_timezone:
            data["studentTimezone"] = self.student_timezone
        if self.student_email:
            data["studentEmail"] = self.student_email
        if self.google_meets_link:
            data["googleMeetsLink"] = self.google_meets_link
        if self.hw_upload_link:
            data["hwUploadLink"] = self.hw_upload_link
        if self.file_request_link:
            data["fileRequestLink"] = self.file_request_link
        if self.number_1:
            data["number1"] = {"phoneNumber": self.number_1.phone_number, "smsEnabled": self.number_1.sms_enabled}
        if self.number_2:
            data["number2"] = {"phoneNumber": self.number_2.phone_number, "smsEnabled": self.number_2.sms_enabled}
        if self.number_3:
            data["number3"] = {"phoneNumber": self.number_3.phone_number, "smsEnabled": self.number_3.sms_enabled}
        if self.hourly_price_1 is not None:
            data["hourlyPrice1"] = self.hourly_price_1
        if self.hourly_price_2 is not None:
            data["hourlyPrice2"] = self.hourly_price_2
        if self.hourly_price_3 is not None:
            data["hourlyPrice3"] = self.hourly_price_3
        if self.hourly_price_4 is not None:
            data["hourlyPrice4"] = self.hourly_price_4
        if self.hourly_price_5 is not None:
            data["hourlyPrice5"] = self.hourly_price_5
        if self.hourly_price_no_show is not None:
            data["hourlyPriceNoShow"] = self.hourly_price_no_show
        if self.payment_collected_by is not None:
            data["paymentCollectedBy"] = self.payment_collected_by.value
        return data

    @classmethod
    def from_dynamodb(cls, item: dict) -> "Student":
        # Parse phone numbers
        number_1 = None
        if item.get("number1"):
            n1 = item["number1"]
            number_1 = PhoneNumber(phone_number=n1["phoneNumber"], sms_enabled=n1.get("smsEnabled", False))

        number_2 = None
        if item.get("number2"):
            n2 = item["number2"]
            number_2 = PhoneNumber(phone_number=n2["phoneNumber"], sms_enabled=n2.get("smsEnabled", False))

        number_3 = None
        if item.get("number3"):
            n3 = item["number3"]
            number_3 = PhoneNumber(phone_number=n3["phoneNumber"], sms_enabled=n3.get("smsEnabled", False))

        n4 = item.get("number4", {"phoneNumber": "18325745458", "smsEnabled": False})
        number_4 = PhoneNumber(phone_number=n4["phoneNumber"], sms_enabled=n4.get("smsEnabled", False))

        n5 = item.get("number5", {"phoneNumber": "18324174712", "smsEnabled": False})
        number_5 = PhoneNumber(phone_number=n5["phoneNumber"], sms_enabled=n5.get("smsEnabled", False))

        return cls(
            student_name=item["studentName"],
            doc_id=item["docId"],
            doc_url=item.get("docUrl"),
            student_timezone=item.get("studentTimezone"),
            student_email=item.get("studentEmail"),
            google_meets_link=item.get("googleMeetsLink"),
            hw_upload_link=item.get("hwUploadLink"),
            file_request_link=item.get("fileRequestLink"),
            number_1=number_1,
            number_2=number_2,
            number_3=number_3,
            number_4=number_4,
            number_5=number_5,
            hourly_price_1=float(item["hourlyPrice1"]) if item.get("hourlyPrice1") is not None else None,
            hourly_price_2=float(item["hourlyPrice2"]) if item.get("hourlyPrice2") is not None else None,
            hourly_price_3=float(item["hourlyPrice3"]) if item.get("hourlyPrice3") is not None else None,
            hourly_price_4=float(item["hourlyPrice4"]) if item.get("hourlyPrice4") is not None else None,
            hourly_price_5=float(item["hourlyPrice5"]) if item.get("hourlyPrice5") is not None else None,
            hourly_price_no_show=float(item["hourlyPriceNoShow"]) if item.get("hourlyPriceNoShow") is not None else None,
            payment_collected_by=PaymentCollector(item["paymentCollectedBy"]) if item.get("paymentCollectedBy") else None,
            created_at=datetime.fromisoformat(item["createdAt"]),
        )


class StudentUpdate(BaseModel):
    """For updating all fields including those set at initialization."""
    doc_url: Optional[str] = None
    student_timezone: Optional[str] = None
    student_email: Optional[str] = None
    google_meets_link: Optional[str] = None
    hw_upload_link: Optional[str] = None
    file_request_link: Optional[str] = None
    number_1: Optional[PhoneNumber] = None
    number_2: Optional[PhoneNumber] = None
    number_3: Optional[PhoneNumber] = None
    number_4: Optional[PhoneNumber] = None
    number_5: Optional[PhoneNumber] = None
    hourly_price_1: Optional[float] = None
    hourly_price_2: Optional[float] = None
    hourly_price_3: Optional[float] = None
    hourly_price_4: Optional[float] = None
    hourly_price_5: Optional[float] = None
    hourly_price_no_show: Optional[float] = None
    payment_collected_by: Optional[PaymentCollector] = None


class StudentPatch(BaseModel):
    """For patching only fields not set at initialization."""
    student_timezone: Optional[str] = None
    student_email: Optional[str] = None
    number_1: Optional[PhoneNumber] = None
    number_2: Optional[PhoneNumber] = None
    number_3: Optional[PhoneNumber] = None
    hourly_price_1: Optional[float] = None
    hourly_price_2: Optional[float] = None
    hourly_price_3: Optional[float] = None
    hourly_price_4: Optional[float] = None
    hourly_price_5: Optional[float] = None
    hourly_price_no_show: Optional[float] = None
    payment_collected_by: Optional[PaymentCollector] = None
