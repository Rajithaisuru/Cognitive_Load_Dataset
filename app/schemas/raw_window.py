from datetime import datetime

from pydantic import BaseModel


class RawWindowInput(BaseModel):
    student_id: str
    lesson_id: str
    session_id: str | None = None
    minute_index: int
    window_start: datetime
    window_end: datetime

