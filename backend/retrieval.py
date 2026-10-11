import os
from pathlib import Path
import chromadb
from dotenv import load_dotenv

load_dotenv()
CHROMA_DIR=os.getenv("CHROMA_DIR", "./data/chroma")
Path(CHROMA_DIR).mkdir(parents=True, exist_ok=True)
_client=chromadb.PersistentClient(path=CHROMA_DIR)
_collection=_client.get_or_create_collection(name="episode_memory")

def index_episode(story_id, episode_number, summary, text, hook):
    doc=f"Episode {episode_number} summary: {summary}\nHook: {hook}\nEpisode text: {text[:6000]}"
    _collection.upsert(ids=[f"{story_id}:{episode_number}"], documents=[doc],
        metadatas=[{"story_id":story_id,"episode_number":int(episode_number)}])

def retrieve_history(story_id, query, current_episode, k=5):
    try:
        result=_collection.query(query_texts=[query], n_results=k,
            where={"$and":[{"story_id":story_id},{"episode_number":{"$lt":int(current_episode)}}]})
        docs=result.get("documents", [[]])[0]
        metas=result.get("metadatas", [[]])[0]
        return [{"episode":m["episode_number"],"content":d} for d,m in zip(docs,metas)]
    except Exception:
        return []
