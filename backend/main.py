from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.database import Base, engine, run_lightweight_migrations
from core.config import settings
import models  # noqa: F401 (ensures models are registered before create_all)
from routers import auth, datasets, analysis, chat

app = FastAPI(title=settings.APP_NAME, version="1.0.0")


@app.on_event("startup")
async def startup_event():
    try:
        Base.metadata.create_all(bind=engine)
        run_lightweight_migrations()
    except Exception as e:
        print(f"Database initialization warning: {e}")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_origin_regex=r"https://insightforge-ai-data-assistant.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(datasets.router)
app.include_router(analysis.router)
app.include_router(chat.router)


@app.get("/")
def root():
    return {"status": "ok", "app": settings.APP_NAME}