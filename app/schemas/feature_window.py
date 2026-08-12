from datetime import datetime

from pydantic import BaseModel


class FeatureWindowInput(BaseModel):
    student_id: str
    lesson_id: str
    session_id: str | None = None
    minute_index: int
    window_start: datetime | None = None
    window_end: datetime | None = None
    pause_frequency: int
    navigation_count_video: int
    rewatch_segments: int
    playback_rate_change: int
    idle_duration_video: int
    time_on_content: int
