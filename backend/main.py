from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from . import db
from .models import StoryCreate,ArcApprove,HumanFeedback,EpisodeReview,RetroactiveChange
from .service import *

@asynccontextmanager
async def lifespan(app):
    db.init_db()
    yield

app=FastAPI(title="Serial Story Agent",version="1.0",lifespan=lifespan)

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/stories")
def stories(): return db.list_stories()

@app.post("/stories")
def create(req:StoryCreate): return create_story(req.title,req.premise)

@app.get("/stories/{story_id}/dashboard")
def get_dashboard(story_id):
    x=dashboard(story_id)
    if not x["story"]: raise HTTPException(404,"Story not found")
    return x

@app.post("/stories/{story_id}/arc/plan")
def arc_plan(story_id):
    try: return plan_arc(story_id)
    except Exception as e: raise HTTPException(500,str(e))

@app.post("/stories/{story_id}/arc/approve")
def arc_approve(story_id,req:ArcApprove):
    approve_arc(story_id,req.approved)
    return {"status":"approved" if req.approved else "rejected"}

@app.post("/stories/{story_id}/feedback")
def feedback(story_id,req:HumanFeedback):
    add_feedback(story_id,req.feedback,req.scope)
    return {"status":"saved"}

@app.post("/stories/{story_id}/episodes/{episode_number}/generate")
def generate(story_id,episode_number):
    try: return generate_episode(story_id,episode_number)
    except Exception as e: raise HTTPException(500,str(e))

@app.post("/stories/{story_id}/episodes/{episode_number}/review")
def review(story_id,episode_number,req:EpisodeReview):
    try:
        return review_episode(story_id,episode_number,req.action,req.feedback,req.edited_text)
    except Exception as e: raise HTTPException(400,str(e))

@app.post("/stories/{story_id}/retroactive")
def retro(story_id,req:RetroactiveChange):
    try:
        return retroactive_change(story_id,req.target_episode,req.feedback,req.invalidated_facts)
    except Exception as e: raise HTTPException(500,str(e))
