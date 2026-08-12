from datetime import datetime

from pydantic import BaseModel


class RawInteractionEventInput(BaseModel):
    student_id: str
    lesson_id: str
    session_id: str | None = None
    event_type: str
    event_time: datetime
    video_time: float | None = None
    from_position: float | None = None
    to_position: float | None = None
    event_value: str | None = None
    question_id: str | None = None
    is_correct: bool | None = None
