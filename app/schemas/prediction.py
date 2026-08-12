from datetime import datetime

from pydantic import BaseModel


class CognitiveLoadInput(BaseModel):
    student_id: str
    lesson_id: str
    session_id: str | None = None
    minute_index: int = 1
    window_start: datetime | None = None
    window_end: datetime | None = None

    pause_frequency: int
    navigation_count_video: int
    rewatch_segments: int
    playback_rate_change: int
    idle_duration_video: int
    time_on_content: int
    navigation_count_adaptation: int = 0
    revisit_frequency: int = 0
    idle_duration_adaptation: int = 0
    quiz_response_time: int = 0
    error_rate: float = 0.0
