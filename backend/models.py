from typing import Optional, List
from pydantic import BaseModel, Field

class StoryCreate(BaseModel):
    premise: str
    title: str = "Untitled Serial"

class ArcApprove(BaseModel):
    approved: bool

class HumanFeedback(BaseModel):
    feedback: str
    scope: str = "future"

class EpisodeReview(BaseModel):
    action: str
    feedback: str = ""
    edited_text: Optional[str] = None

class RetroactiveChange(BaseModel):
    target_episode: int
    feedback: str
    invalidated_facts: List[str] = Field(default_factory=list)
