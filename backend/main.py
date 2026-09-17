"""
FastAPI-приложение Movie-Rec.

Роуты — тонкие обёртки над services.py и auth.py.
Алгоритмы живут в algorithms/ и вызываются через services.
"""
import sys
import os

# --- sys.path fix
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import logging
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from backend.db import engine, SessionLocal, get_db
from backend.models import Base, Movie, Genre, User, Interaction
from backend.schemas import (
    UserCreate, UserLogin, UserOut, Token,
    MovieOut, MovieBrief, PaginatedMovies,
    InteractionIn, InteractionOut, MovieStateOut,
    SimilarOut, RecommendationOut,
    AlgorithmInfo, CompareResult,
)
from backend.auth import (
    create_token, require_user,
    register_user, authenticate_user, hash_password,
)
from backend.services import (
    record_interaction, delete_interaction, get_user_state,
    get_user_movies_by_status, get_movie_or_404,
    get_similar_movies, get_recommendations,
    compare_algorithms, rebuild_algorithm_cache,
)

logger = logging.getLogger("movie_rec")
logging.basicConfig(level=logging.INFO)


# ==============================
# LIFESPAN
# ==============================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Creating database tables if not exist...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            demo = User(
                username="demo",
                password_hash=hash_password("demo"),
            )
            db.add(demo)
            db.commit()
            logger.info("Created demo user (demo/demo)")
    finally:
        db.close()
    yield


# ==============================
# APP
# ==============================
app = FastAPI(
    title="Movie-Rec API",
    description="Каталог фильмов + рекомендательная система",
    version="0.1.0",
    lifespan=lifespan,
)

# ── FIX #2: allow_credentials=False (JWT в Authorization header, не в cookie)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================
# STATIC FRONTEND
# ==============================
_FRONTEND_DIR = os.path.join(_ROOT, "frontend")
if os.path.isdir(_FRONTEND_DIR):
    app.mount(
        "/app",
        StaticFiles(directory=_FRONTEND_DIR, html=True),
        name="frontend",
    )
    logger.info(f"Frontend mounted at /app → {_FRONTEND_DIR}")


# ==============================
# AUTH
# ==============================
@app.post("/auth/register", response_model=Token, status_code=201)
def register(body: UserCreate, db: Session = Depends(get_db)):
    user = register_user(db, body.username, body.password, body.email)
    return Token(access_token=create_token(user.id))


@app.post("/auth/login", response_model=Token)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = authenticate_user(db, body.username, body.password)
    return Token(access_token=create_token(user.id))


@app.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(require_user)):
    return user


# ==============================
# MOVIES
# ==============================
@app.get("/movies", response_model=PaginatedMovies)
def list_movies(
    db: Session = Depends(get_db),
    q: str = Query("", description="Search by title"),
    genre: str = Query("", description="Genre name"),
    year: Optional[int] = Query(None, description="Year from"),
    sort: str = Query("popularity", pattern="^(popularity|year|rating|title)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    query = db.query(Movie)

    if q:
        query = query.filter(Movie.title.ilike(f"%{q}%"))

    # ── FIX #1: Movie.genres.any() вместо join — без дублей
    if genre:
        query = query.filter(
            Movie.genres.any(Genre.name.ilike(f"%{genre}%"))
        )

    if year:
        query = query.filter(Movie.year >= year)

    if sort == "popularity":
        query = query.order_by(desc(Movie.popularity))
    elif sort == "year":
        query = query.order_by(desc(Movie.year))
    elif sort == "rating":
        query = query.order_by(desc(Movie.vote_average))
    else:
        query = query.order_by(Movie.title)

    total = query.count()
    items = query.offset((page - 1) * limit).limit(limit).all()

    return PaginatedMovies(
        items=[MovieBrief.model_validate(m) for m in items],
        total=total,
        page=page,
        limit=limit,
        pages=(total + limit - 1) // limit if total else 0,
    )


@app.get("/movies/{movie_id}", response_model=MovieOut)
def get_movie(movie_id: int, db: Session = Depends(get_db)):
    return get_movie_or_404(db, movie_id)


@app.get("/movies/{movie_id}/similar", response_model=list[SimilarOut])
def get_similar(
    movie_id: int,
    algorithm: str = Query("item_item"),
    k: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_similar_movies(db, movie_id, algorithm, k)


# ==============================
# INTERACTIONS
# ==============================
@app.post("/interactions", response_model=InteractionOut, status_code=201)
def add_interaction(
    body: InteractionIn,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return record_interaction(db, user, body.movie_id, body.event_type, body.value)


@app.delete("/interactions/{movie_id}", status_code=204)
def delete_interaction_route(
    movie_id: int,
    event_type: str = Query(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    delete_interaction(db, user, movie_id, event_type)
    return None


@app.get("/users/me/state/{movie_id}", response_model=MovieStateOut)
def get_my_state(
    movie_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    state = get_user_state(db, user, movie_id)
    if not state:
        return MovieStateOut(movie_id=movie_id)
    return state


@app.get("/users/me/watched", response_model=list[MovieBrief])
def get_watched(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    movies = get_user_movies_by_status(db, user, "watched")
    return [MovieBrief.model_validate(m) for m in movies]


@app.get("/users/me/watchlist", response_model=list[MovieBrief])
def get_watchlist(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    movies = get_user_movies_by_status(db, user, "want_to_watch")
    return [MovieBrief.model_validate(m) for m in movies]


# ==============================
# RECOMMENDATIONS
# ==============================
@app.get("/recommendations/me", response_model=list[RecommendationOut])
def recommendations(
    algorithm: str = Query("popularity"),
    k: int = Query(20, ge=1, le=100),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return get_recommendations(db, user, algorithm, k)


# ==============================
# ALGORITHMS (dev)
# ==============================
_DEFAULT_ALGORITHMS = [
    {"name": "popularity", "display_name": "Популярность",          "type": "baseline",      "complexity": "O(n)"},
    {"name": "jaccard",    "display_name": "Jaccard Similarity",    "type": "content",       "complexity": "O(n·g)"},
    {"name": "tfidf",      "display_name": "TF-IDF Cosine",         "type": "content",       "complexity": "O(n·d)"},
    {"name": "item_item",  "display_name": "Item-Item CF",          "type": "collaborative", "complexity": "O(n²·u)"},
    {"name": "mf",         "display_name": "Matrix Factorization",  "type": "collaborative", "complexity": "O(n·k·i)"},
]


@app.get("/algorithms/list", response_model=list[AlgorithmInfo])
def list_algorithms():
    try:
        from algorithms.registry import REGISTRY
        available = set(REGISTRY.keys())
    except Exception:
        available = set()

    return [
        AlgorithmInfo(**a, available=(a["name"] in available))
        for a in _DEFAULT_ALGORITHMS
    ]


@app.get("/algorithms/compare", response_model=CompareResult)
def compare(
    movie_id: int = Query(...),
    k: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    result = compare_algorithms(db, movie_id, k)
    return CompareResult(**result)


@app.post("/algorithms/rebuild", status_code=202)
def rebuild(
    algorithm: str = Query(...),
    db: Session = Depends(get_db),
):
    return rebuild_algorithm_cache(db, algorithm)


# ==============================
# HEALTH
# ==============================
@app.get("/")
def root():
    return {
        "service": "Movie-Rec API",
        "docs": "/docs",
        "frontend": "/app/",
        "time": datetime.utcnow().isoformat(),
    }


@app.get("/health")
def health(db: Session = Depends(get_db)):
    return {
        "status": "ok",
        "movies": db.query(func.count(Movie.id)).scalar(),
        "users": db.query(func.count(User.id)).scalar(),
        "interactions": db.query(func.count(Interaction.id)).scalar(),
    }


# ==============================
# ENTRY
# ==============================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)