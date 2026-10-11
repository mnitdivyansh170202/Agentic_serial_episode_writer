import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Serial Story Agent", page_icon="📚", layout="wide")
st.title("📚 200-Episode Serial Story Agent")
st.caption("Streamlit + FastAPI + LangGraph + GPT + SQLite")


def api(method, path, payload=None):
    try:
        r = requests.request(
            method,
            BACKEND + path,
            json=payload,
            timeout=900,
        )
        if r.status_code >= 400:
            st.error(f"Backend error ({r.status_code}): {r.text}")
            return None
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error(f"Cannot connect to backend at {BACKEND}. Make sure FastAPI is running.")
        return None
    except Exception as e:
        st.error(f"Request failed: {e}")
        return None


if "selected_story_id" not in st.session_state:
    st.session_state.selected_story_id = None


stories = api("GET", "/stories") or []

story_options = {
    f'{x["title"]} ({x["story_id"]})': x["story_id"]
    for x in stories
}


with st.sidebar:
    st.header("📖 Story")

    st.subheader("Create New Story")

    title = st.text_input("Title", "The Last Delivery")

    premise = st.text_area(
        "One-line premise",
        "A delivery rider realizes every address on today's route "
        "belongs to someone who died in the same building.",
    )

    if st.button("➕ Create Story", type="primary"):
        if not title.strip():
            st.warning("Please enter a story title.")
        elif not premise.strip():
            st.warning("Please enter a premise.")
        else:
            with st.spinner("Creating story..."):
                result = api(
                    "POST",
                    "/stories",
                    {"title": title, "premise": premise},
                )

            if result:
                # Automatically select the newly-created story.
                st.session_state.selected_story_id = result["story_id"]
                st.success("Story created!")
                st.rerun()

    st.divider()
    st.subheader("Existing Stories")

    if story_options:
        labels = list(story_options.keys())
        selected_id = st.session_state.selected_story_id
        default_index = 0

        if selected_id is not None:
            for i, label in enumerate(labels):
                if story_options[label] == selected_id:
                    default_index = i
                    break

        selected_label = st.selectbox(
            "Select story",
            labels,
            index=default_index,
        )

        st.session_state.selected_story_id = story_options[selected_label]
    else:
        st.info("No stories created yet.")
        st.stop()


story_id = st.session_state.selected_story_id

if not story_id:
    st.info("Create or select a story from the sidebar.")
    st.stop()


dashboard = api("GET", f"/stories/{story_id}/dashboard")

if not dashboard:
    st.error("Could not load the story dashboard.")
    st.stop()

story = dashboard["story"]
episodes = dashboard.get("episodes", [])

# Derive progress from persisted episode records as well as the database counter.
# This repairs a stale counter in the UI without requiring an extra API endpoint.
episodes_by_number = {int(ep["episode_number"]): ep for ep in episodes}
approved_statuses = {"approved", "approved_after_human_edit"}
consecutive_approved = 0
while consecutive_approved + 1 in episodes_by_number and episodes_by_number[consecutive_approved + 1]["status"] in approved_statuses:
    consecutive_approved += 1
current_episode_display = max(int(story.get("current_episode", 0) or 0), consecutive_approved)

st.header(f'📖 {story["title"]}')

c1, c2, c3, c4 = st.columns(4)

c1.metric("Status", story["status"])
c2.metric("Current Episode", current_episode_display)
c3.metric("Revision", story["version"])
c4.metric("LLM Cost", f'${dashboard["total_cost"]:.6f}')

st.divider()


arc_tab, episodes_tab, feedback_tab, retro_tab, cost_tab, limits_tab = st.tabs(
    [
        "🧭 Story Arc",
        "📚 Episodes",
        "👤 HITL Feedback",
        "🔄 Retroactive Edit",
        "💰 Cost",
        "⚠️ Limitations",
    ]
)


with arc_tab:
    st.subheader("Story Bible & 200-Episode Arc")

    if not story["arc"]:
        st.info(
            "The story has been created, but the Story Bible and "
            "200-episode arc have not been generated yet."
        )

        if st.button(
            "🚀 Generate Story Bible + 200-Episode Arc",
            type="primary",
        ):
            with st.spinner("Planning story bible and 200-episode arc..."):
                result = api("POST", f"/stories/{story_id}/arc/plan")

            if result:
                st.success("Story arc generated.")
                st.rerun()

    else:
        if dashboard.get("story_bible"):
            st.subheader("Story Bible")
            st.json(dashboard["story_bible"])

        arc = story["arc"]

        st.subheader("Logline")
        st.write(arc.get("logline", ""))

        st.subheader("Major Turning Points")
        for x in arc.get("major_turning_points", []):
            st.write("•", x)

        st.subheader("Character Arcs")
        for x in arc.get("character_arcs", []):
            st.write("•", x)

        st.subheader("Major Plot Threads")
        for x in arc.get("major_threads", []):
            st.write("•", x)

        st.subheader("200-Episode Plan")

        with st.expander("View all episode beats"):
            for i, beat in enumerate(arc.get("episode_beats", []), 1):
                st.markdown(f"**Episode {i}** — {beat}")

        if story["status"] == "arc_pending_approval":
            st.warning("The story arc is waiting for human approval.")

            a, b = st.columns(2)

            if a.button("✅ Approve Arc", type="primary"):
                result = api(
                    "POST",
                    f"/stories/{story_id}/arc/approve",
                    {"approved": True},
                )
                if result:
                    st.success("Arc approved.")
                    st.rerun()

            if b.button("❌ Reject Arc"):
                result = api(
                    "POST",
                    f"/stories/{story_id}/arc/approve",
                    {"approved": False},
                )
                if result:
                    st.rerun()

        elif story["status"] == "ready":
            st.success("✅ Arc approved. You can now generate episodes.")


with episodes_tab:
    st.subheader("📚 Generated Episodes")

    # The next episode is the first episode that has not been approved.
    # This avoids regenerating Episode 1 when its DB counter is stale.
    next_episode = consecutive_approved + 1
    existing_next_episode = episodes_by_number.get(next_episode)

    if (
        story["arc"]
        and story["status"] in ["ready", "revising"]
        and next_episode <= 200
    ):
        if existing_next_episode and existing_next_episode["status"] not in approved_statuses:
            st.warning(
                f"Episode {next_episode} already exists with status "
                f"'{existing_next_episode['status']}'. Review, edit, or approve "
                "that episode below instead of generating it again."
            )
        else:
            st.info(f"Next episode available: Episode {next_episode}")

            if st.button(
                f"✍️ Generate Episode {next_episode}",
                type="primary",
            ):
                with st.spinner(f"Generating Episode {next_episode}..."):
                    result = api(
                        "POST",
                        f"/stories/{story_id}/episodes/{next_episode}/generate",
                    )

                if result:
                    st.success(f"Episode {next_episode} generated.")
                    st.rerun()

    elif next_episode > 200:
        st.success("🎉 All 200 episodes have been approved.")
    else:
        st.info("Approve the story arc before generating episodes.")

    st.divider()

    if not episodes:
        st.info("No episodes have been generated yet.")
    else:
        st.subheader(f"{len(episodes)} Episode(s) Generated")

        for ep in reversed(episodes):
            number = ep["episode_number"]

            with st.expander(
                f'Episode {number} · {ep["status"]}',
                expanded=(number == current_episode_display),
            ):
                st.markdown(f"## Episode {number}")
                st.write(ep["text"])

                st.divider()

                a, b = st.columns(2)

                a.metric(
                    "Word Count",
                    len(ep["text"].split()),
                )

                b.write("**Hook:**")
                b.write(ep["hook"])

                st.write("**Episode Crux:**")
                st.write(ep["summary"])

                st.write("**Facts Introduced:**")
                st.write(ep["facts_introduced"])

                if ep["status"] in ["draft", "needs_revision"]:
                    st.divider()
                    st.subheader("Human Review")

                    action = st.radio(
                        "Action",
                        ["Approve", "Edit", "Reject"],
                        horizontal=True,
                        key=f"action_{number}",
                    )

                    feedback = st.text_area(
                        "Feedback",
                        key=f"feedback_{number}",
                    )

                    edited_text = None

                    if action == "Edit":
                        edited_text = st.text_area(
                            "Edited Episode",
                            ep["text"],
                            height=400,
                            key=f"edited_{number}",
                        )

                    if st.button(
                        "Submit Review",
                        key=f"submit_{number}",
                    ):
                        result = api(
                            "POST",
                            f"/stories/{story_id}/episodes/{number}/review",
                            {
                                "action": action.lower(),
                                "feedback": feedback,
                                "edited_text": edited_text,
                            },
                        )

                        if result:
                            st.success("Episode review submitted.")
                            st.rerun()


with feedback_tab:
    st.subheader("👤 Persistent Human Decisions")

    st.write(
        "These decisions are persisted and should influence future episode generation."
    )

    feedback = st.text_area(
        "Decision / instruction",
        placeholder="Example: Slow down the romance between Arjun and Meera.",
    )

    scope = st.selectbox(
        "Scope",
        ["future", "current_arc", "global"],
    )

    if st.button("💾 Save Decision", type="primary"):
        if feedback.strip():
            result = api(
                "POST",
                f"/stories/{story_id}/feedback",
                {"feedback": feedback, "scope": scope},
            )

            if result:
                st.success("Decision saved.")
                st.rerun()
        else:
            st.warning("Please enter a decision.")

    st.divider()
    st.subheader("Active Decisions")

    decisions = dashboard.get("decisions", [])

    if decisions:
        for x in decisions:
            st.write("•", x)
    else:
        st.info("No human decisions recorded yet.")


with retro_tab:
    st.subheader("🔄 Retroactive Story Change")

    st.write(
        "Change an earlier episode/fact and replay the affected downstream story."
    )

    max_episode = max(1, story["current_episode"])

    target = st.number_input(
        "Target Episode",
        min_value=1,
        max_value=max_episode,
        value=1,
    )

    change = st.text_area(
        "What should change?",
        "Remove the fact that Meera knows about the building.",
    )

    facts = st.text_area(
        "Invalidated canonical facts, one per line",
        "Meera knows about the building",
    )

    if st.button("🔄 Create Revision + Replay", type="primary"):
        payload = {
            "target_episode": int(target),
            "feedback": change,
            "invalidated_facts": [
                x.strip()
                for x in facts.splitlines()
                if x.strip()
            ],
        }

        with st.spinner("Running impact analysis and downstream replay..."):
            result = api(
                "POST",
                f"/stories/{story_id}/retroactive",
                payload,
            )

        if result:
            st.success(result["message"])
            st.subheader("Impact Analysis")
            st.json(result["impact"])
            st.rerun()


with cost_tab:
    st.subheader("💰 LLM Usage & Cost")

    usage = dashboard.get("usage", [])

    if usage:
        st.dataframe(usage, use_container_width=True)
        st.metric(
            "Total LLM Cost",
            f'${dashboard["total_cost"]:.6f}',
        )
    else:
        st.info("No LLM calls yet.")


with limits_tab:
    st.subheader("⚠️ Known Failure Modes")

    st.markdown("""
### Long-horizon drift
The 200-episode plan can become stale. Periodic replanning may be required.

### Conflicting human edits
Conflicting instructions should be surfaced rather than silently resolved.

### Retroactive cascades
Changing an old fact can invalidate many downstream episodes. The system creates a revision and replays from the earliest affected point.

### Retrieval misses
Historical semantic retrieval can miss or mis-rank events. Canonical SQLite state remains authoritative.

### Consistency ≠ quality
An episode can be consistent but still boring or generic. Human review and quality evaluation remain necessary.

### LLM validator limitations
Semantic validation can miss subtle contradictions. Deterministic checks should be used wherever possible.

### State extraction errors
Incorrectly extracted facts can contaminate future generation. High-impact state changes should ideally be validated before becoming canonical.
""")
