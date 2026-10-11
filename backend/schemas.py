from typing import List
from pydantic import BaseModel, Field

class ArcPlan(BaseModel):
    logline: str
    acts: List[str]
    major_turning_points: List[str]
    character_arcs: List[str]
    major_threads: List[str]
    episode_beats: List[str] = Field(description="Exactly 200 concise episode beats.")

class EpisodePlan(BaseModel):
    purpose: str
    characters: List[str]
    required_events: List[str]
    must_not_happen: List[str]
    threads_to_advance: List[str]
    hook: str

class EpisodeExtraction(BaseModel):
    summary: str
    facts_introduced: List[str]
    facts_used: List[str]
    characters_changed: List[str]
    threads_advanced: List[str]
    hook: str

class ContinuityResult(BaseModel):
    passed: bool
    issues: List[str]
    suggestions: List[str]


class StoryBible(BaseModel):
    title: str
    logline: str
    protagonist: str
    major_characters: List[str]
    relationships: List[str]
    world_rules: List[str]
    central_mystery: str
    durable_facts: List[str]
