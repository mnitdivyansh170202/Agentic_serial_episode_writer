
import uuid

from . import db
from .llm import structured_call
from .schemas import ArcPlan, EpisodeExtraction, StoryBible
from .graph import GRAPH, context_for


def create_story(title, premise):
    """Create a new story and return its database record."""
    if not premise or not premise.strip():
        raise ValueError("Story premise cannot be empty.")

    title = (title or "Untitled Serial").strip()
    premise = premise.strip()

    story_id = uuid.uuid4().hex[:8]
    db.create_story(story_id, title, premise)

    return db.get_story(story_id)


def plan_arc(story_id):
    """
    Generate the Story Bible and a complete 200-episode arc.
    The generated arc remains pending until human approval.
    """
    story = db.get_story(story_id)

    if not story:
        raise ValueError(f"Story not found: {story_id}")

    bible_prompt = f"""
Create a durable Story Bible for a 200-episode serial.

Include:
- Title
- Logline
- Protagonist
- Major characters
- Relationships
- World rules
- Central mystery
- Durable facts that must remain consistent

Make the information specific, coherent, and useful for maintaining
continuity across all 200 episodes.

PREMISE:
{story["premise"]}
"""

    bible = structured_call(
        bible_prompt,
        StoryBible,
        "story_bible",
        story_id,
        "story_bible",
    )

    db.save_story_bible(story_id, bible.model_dump())

    arc_prompt = f"""
Plan a complete 200-episode serial.

PREMISE:
{story["premise"]}

STORY BIBLE:
{bible.model_dump_json()}

Create:
- A coherent overall arc
- Acts and major turning points
- Character arcs
- Major unresolved plot threads
- Exactly 200 concise episode-level beats

Each eventual episode must be 400-700 words and end with a compelling
hook. Vary pacing. Not every episode should contain a major twist.

Ensure the episode beats progress logically, preserve character
motivations, advance existing plot threads, and avoid contradictions.
"""

    arc = structured_call(
        arc_prompt,
        ArcPlan,
        "arc_plan",
        story_id,
        "arc_planner",
    )

    if len(arc.episode_beats) != 200:
        raise ValueError(
            f"Planner returned {len(arc.episode_beats)} episode beats; "
            "expected exactly 200."
        )

    db.update_story(
        story_id,
        arc_json=arc.model_dump_json(),
        status="arc_pending_approval",
    )

    updated_story = db.get_story(story_id)

    return {
        "story_bible": db.get_story_bible(story_id),
        "arc": updated_story["arc"],
    }


def approve_arc(story_id, approved):
    """Approve or reject the proposed story arc."""
    story = db.get_story(story_id)

    if not story:
        raise ValueError(f"Story not found: {story_id}")

    if approved and not story.get("arc"):
        raise ValueError("Cannot approve an arc that has not been generated.")

    db.update_story(
        story_id,
        status="ready" if approved else "arc_rejected",
    )

    return {
        "story_id": story_id,
        "status": "ready" if approved else "arc_rejected",
    }


def add_feedback(story_id, feedback, scope="future"):
    """Persist human feedback as an active story decision."""
    if not feedback or not feedback.strip():
        raise ValueError("Feedback cannot be empty.")

    story = db.get_story(story_id)

    if not story:
        raise ValueError(f"Story not found: {story_id}")

    db.add_decision(story_id, feedback.strip(), scope)

    return {
        "story_id": story_id,
        "feedback": feedback.strip(),
        "scope": scope,
    }


def generate_episode(story_id, episode_number):
    """Generate, validate, extract state from, and index an episode."""    
    try:
        episode_number = int(episode_number)
    except (TypeError, ValueError):
        raise ValueError("episode_number must be a positive integer.")

    if episode_number < 1:
        raise ValueError("episode_number must be a positive integer.")


    story = db.get_story(story_id)

    if not story:
        raise ValueError(f"Story not found: {story_id}")

    if story.get("status") != "ready" and story.get("status") != "revising":
        raise ValueError(
            "The story arc must be approved before generating episodes."
        )

    arc = story.get("arc") or {}
    beats = arc.get("episode_beats", [])

    if episode_number > len(beats):
        raise ValueError(
            f"Episode {episode_number} is outside the planned arc."
        )

    state = {
        "story_id": story_id,
        "episode_number": episode_number,
        "context": context_for(story_id, episode_number),
    }

    result = GRAPH.invoke(state)

    extraction = result["extraction"]
    validation = result["validation"]

    episode = {
        "episode_number": episode_number,
        "text": result["draft"],
        "summary": extraction["summary"],
        "facts_introduced": extraction["facts_introduced"],
        "facts_used": extraction["facts_used"],
        "characters_changed": extraction["characters_changed"],
        "threads_advanced": extraction["threads_advanced"],
        "hook": extraction["hook"],
        "status": "draft" if validation["passed"] else "needs_revision",
        "version": story["version"],
    }

    db.save_episode(story_id, episode)

    from .retrieval import index_episode

    index_episode(
        story_id,
        episode_number,
        episode["summary"],
        episode["text"],
        episode["hook"],
    )

    return {
        "episode": episode,
        "validation": validation,
    }


def review_episode(
    story_id,
    episode_number,
    action,
    feedback="",
    edited_text=None,
):
    """Approve, reject, or save a human-edited episode."""
    episode = db.get_episode(story_id, episode_number)

    if not episode:
        raise ValueError("Episode not found.")

    if action == "reject":
        db.delete_episode(story_id, episode_number)

        return {"status": "rejected"}

    if action == "edit":
        if not edited_text or not edited_text.strip():
            raise ValueError("edited_text is required for an edit.")

        edited_text = edited_text.strip()

        extraction = structured_call(
            (
                "Extract durable story state from this human-edited episode. "
                "Do not invent facts. Summarize what actually happens, "
                "identify facts introduced and used, track character changes "
                "and plot threads, and identify the ending hook.\n\n"
                f"EPISODE:\n{edited_text}"
            ),
            EpisodeExtraction,
            "human_edit_extraction",
            story_id,
            "human_edit_state_extractor",
            episode_number,
        )

        episode.update(
            {
                "text": edited_text,
                "summary": extraction.summary,
                "facts_introduced": extraction.facts_introduced,
                "facts_used": extraction.facts_used,
                "characters_changed": extraction.characters_changed,
                "threads_advanced": extraction.threads_advanced,
                "hook": extraction.hook,
            }
        )

        episode["status"] = "approved_after_human_edit"

    elif action == "approve":
        episode["status"] = "approved"

    else:
        raise ValueError("action must be 'approve', 'edit', or 'reject'.")

    db.save_episode(story_id, episode)

    for fact in episode.get("facts_introduced", []):
        db.add_fact(story_id, fact, episode_number)

    if feedback and feedback.strip():
        db.add_decision(story_id, feedback.strip(), "future")

    
    story = db.get_story(story_id)

    current_episode = int(story.get("current_episode") or 0)
    reviewed_episode = int(episode_number)

    db.update_story(
        story_id,
        current_episode=max(current_episode, reviewed_episode),
        status="ready",
    )

    return {
        "status": episode["status"],
        "episode": episode,
    }


def impact_analysis(story_id, target_episode, invalidated_facts):
    """Identify later episodes that rely on facts being invalidated."""
    if target_episode < 1:
        raise ValueError("target_episode must be a positive integer.")

    affected_episodes = []
    invalidated = set(invalidated_facts or [])

    for episode in db.list_episodes(story_id):
        if episode["episode_number"] <= target_episode:
            continue

        facts_used = set(episode.get("facts_used", []))

        if facts_used.intersection(invalidated):
            affected_episodes.append(episode["episode_number"])

    return {
        "target_episode": target_episode,
        "invalidated_facts": list(invalidated),
        "affected_episodes": affected_episodes,
        "replay_from": target_episode,
    }


def retroactive_change(
    story_id,
    target_episode,
    feedback,
    invalidated_facts,
):
    """
    Record a retroactive change and regenerate episodes from the target
    episode through the last completed episode.
    """
    story = db.get_story(story_id)

    if not story:
        raise ValueError(f"Story not found: {story_id}")

    if target_episode < 1:
        raise ValueError("target_episode must be a positive integer.")

    if not feedback or not feedback.strip():
        raise ValueError("Retroactive-change feedback cannot be empty.")

    current_episode = story["current_episode"]

    if target_episode > current_episode:
        raise ValueError(
            "The target episode must not be beyond the last completed episode."
        )

    impact = impact_analysis(
        story_id,
        target_episode,
        invalidated_facts or [],
    )

    new_version = story["version"] + 1

    db.update_story(
        story_id,
        version=new_version,
        status="revising",
    )

    db.add_decision(
        story_id,
        (
            f"RETROACTIVE CHANGE @ Episode {target_episode}: "
            f"{feedback.strip()}"
        ),
        f"episode_{target_episode}_onward",
    )

    for fact in invalidated_facts or []:
        db.deactivate_fact(story_id, fact)

    # Delete the old versions before replaying the story sequentially.
    for number in range(target_episode, current_episode + 1):
        db.delete_episode(story_id, number)

    try:
        for number in range(target_episode, current_episode + 1):
            generate_episode(story_id, number)
    except Exception:
        # Keep the story marked as revising so a failed replay is visible.
        raise

    db.update_story(story_id, status="ready")

    return {
        "version": new_version,
        "impact": impact,
        "message": (
            f"Created story revision v{new_version}; "
            f"replayed from Episode {target_episode}."
        ),
    }


def dashboard(story_id):
    """Return the story state used by the dashboard UI."""
    story = db.get_story(story_id)

    if not story:
        raise ValueError(f"Story not found: {story_id}")

    return {
        "story": story,
        "story_bible": db.get_story_bible(story_id),
        "episodes": db.list_episodes(story_id),
        "decisions": db.get_active_decisions(story_id),
        "facts": db.get_active_facts(story_id),
        "usage": db.get_usage(story_id),
        "total_cost": db.get_total_cost(story_id),
    }
