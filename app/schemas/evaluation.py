from datetime import datetime

from pydantic import BaseModel, Field


class EvaluationSessionInput(BaseModel):
    video_id: str = Field(min_length=1, max_length=50)


class EvaluationPredictionInput(BaseModel):
    participant_id: str = Field(min_length=2, max_length=50)
    session_id: str = Field(min_length=2, max_length=100)
    video_id: str = Field(min_length=1, max_length=50)
    segment_index: int = Field(ge=1)
    segment_start_time: datetime
    segment_end_time: datetime
    pause_frequency: int = Field(ge=0)
    navigation_count_video: int = Field(ge=0)
    rewatch_segments: int = Field(ge=0)
    playback_rate_change: int = Field(ge=0)
    idle_duration_video: int = Field(ge=0)
    time_on_content: int = Field(ge=0)


class EvaluationRatingInput(BaseModel):
    evaluation_id: str = Field(min_length=36, max_length=36)
    participant_id: str = Field(min_length=2, max_length=50)
    session_id: str = Field(min_length=2, max_length=100)
    participant_rating: int = Field(ge=1, le=5)
