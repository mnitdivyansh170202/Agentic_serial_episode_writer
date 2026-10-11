from typing import Any, Dict, TypedDict
from langgraph.graph import StateGraph, START, END
from . import db
from .llm import text_call, structured_call
from .schemas import EpisodePlan, EpisodeExtraction, ContinuityResult
from .retrieval import retrieve_history

class StoryGraphState(TypedDict, total=False):
    story_id: str
    episode_number: int
    context: Dict[str, Any]
    episode_plan: Dict[str, Any]
    draft: str
    extraction: Dict[str, Any]
    validation: Dict[str, Any]

def context_for(story_id, episode_number):
    story = db.get_story(story_id)
    eps = db.list_episodes(story_id)
    beats = story["arc"].get("episode_beats", [])
    current_beat = beats[episode_number-1] if len(beats) >= episode_number else ""

    recent = [
        {"episode":e["episode_number"],"summary":e["summary"],"hook":e["hook"],
         "facts":e["facts_introduced"]}
        for e in eps if e["episode_number"] < episode_number
    ][-3:]

    # Historical RAG is supplementary; episode-number filtering prevents future leakage.
    historical = retrieve_history(story_id, current_beat or story["premise"], episode_number, k=5)

    return {
        "premise":story["premise"],
        "story_bible":db.get_story_bible(story_id),
        "episode":episode_number,
        "current_beat":current_beat,
        "recent":recent,
        "historical":historical,
        "canon_facts":db.get_active_facts(story_id),
        "decisions":db.get_active_decisions(story_id)
    }

def plan_node(s):
    c=s["context"]
    p=f"""
Plan Episode {c["episode"]} for a 200-episode serial.

PREMISE:
{c["premise"]}

STORY BIBLE:
{c["story_bible"]}

ARC BEAT:
{c["current_beat"]}

CANON FACTS:
{c["canon_facts"]}

ACTIVE HUMAN DECISIONS:
{c["decisions"]}

RECENT:
{c["recent"]}

RELEVANT HISTORY:
{c["historical"]}

Create a focused episode plan. Advance the story and do not contradict canon.
"""
    x=structured_call(p,EpisodePlan,"episode_plan",s["story_id"],"episode_planner",c["episode"])
    return {"episode_plan":x.model_dump()}

def writer_node(s):
    c=s["context"]
    p=f"""
Write Episode {c["episode"]} of the serial.

PREMISE:
{c["premise"]}

STORY BIBLE:
{c["story_bible"]}

ARC BEAT:
{c["current_beat"]}

CANON:
{c["canon_facts"]}

HUMAN DECISIONS:
{c["decisions"]}

RECENT EPISODES:
{c["recent"]}

RELEVANT HISTORY:
{c["historical"]}

EPISODE PLAN:
{s["episode_plan"]}

Rules:
- 400-700 words.
- Preserve continuity.
- Advance at least one plot thread.
- Avoid generic filler and repeated beats.
- End on a meaningful hook.
Return only prose.
"""
    return {"draft":text_call(p,s["story_id"],"episode_writer",c["episode"])}

def validate_node(s):
    c=s["context"]
    words=len(s["draft"].split())
    deterministic=[]
    if not 400 <= words <= 700:
        deterministic.append(f"Word count is {words}; required range is 400-700.")

    p=f"""
Check the episode for continuity and story quality.

CANON:
{c["canon_facts"]}

HUMAN DECISIONS:
{c["decisions"]}

RECENT:
{c["recent"]}

PLAN:
{s["episode_plan"]}

EPISODE:
{s["draft"]}

Check contradictions, character consistency, plot advancement, repeated beats,
and whether the ending is a meaningful hook.
"""
    x=structured_call(p,ContinuityResult,"continuity_result",
                      s["story_id"],"continuity_checker",c["episode"])
    issues=deterministic+x.issues
    return {"validation":{
        "passed":not issues and x.passed,
        "issues":issues,
        "suggestions":x.suggestions,
        "word_count":words
    }}

def extract_node(s):
    c=s["context"]
    p=f"""
Extract durable story state from the approved draft below.

EPISODE:
{s["draft"]}

PREVIOUS CANON:
{c["canon_facts"]}

Do not invent facts. Return a concise summary, introduced facts, facts used,
character changes, plot threads advanced, and the ending hook.
"""
    x=structured_call(p,EpisodeExtraction,"episode_extraction",
                      s["story_id"],"state_extractor",c["episode"])
    return {"extraction":x.model_dump()}

def build_graph():
    b=StateGraph(StoryGraphState)
    b.add_node("plan_episode",plan_node)
    b.add_node("write_episode",writer_node)
    b.add_node("validate",validate_node)
    b.add_node("extract_state",extract_node)
    b.add_edge(START,"plan_episode")
    b.add_edge("plan_episode","write_episode")
    b.add_edge("write_episode","validate")
    b.add_edge("validate","extract_state")
    b.add_edge("extract_state",END)
    return b.compile()

GRAPH=build_graph()
