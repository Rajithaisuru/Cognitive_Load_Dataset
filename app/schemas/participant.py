from pydantic import BaseModel


class ParticipantCreateInput(BaseModel):
    lesson_id: str
