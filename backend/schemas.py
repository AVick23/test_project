"""
Pydantic-схемы для API.
"""
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ==============================
# HELPERS
# ==============================
def _genres_to_names(v):
    """ORM Genre -> list[str] для Pydantic."""
    if not v:
        return []
    return [g.name if hasattr(g, "name") else str(g) for g in v]


# ==============================
# AUTH
# ==============================
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=4, max_length=128)
    email: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: Optional[str] = None
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ==============================
# MOVIES
# ==============================
class MovieOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tmdb_id: Optional[int] = None
    title: str
    original_title: Optional[str] = None
    year: Optional[int] = None
    runtime: Optional[int] = None
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    original_language: Optional[str] = None
    popularity: Optional[float] = 0.0
    vote_average: Optional[float] = 0.0
    vote_count: Optional[int] = 0
    genres: list[str] = []

    @field_validator("genres", mode="before")
    @classmethod
    def _genres(cls, v):
        return _genres_to_names(v)


class MovieBrief(BaseModel):
    """Короткая версия для списков."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    year: Optional[int] = None
    poster_path: Optional[str] = None
    vote_average: Optional[float] = 0.0
    genres: list[str] = []

    @field_validator("genres", mode="before")
    @classmethod
    def _genres(cls, v):
        return _genres_to_names(v)


class PaginatedMovies(BaseModel):
    items: list[MovieBrief]
    total: int
    page: int
    limit: int
    pages: int


# ==============================
# INTERACTIONS
# ==============================
class InteractionIn(BaseModel):
    movie_id: int
    event_type: Literal[
        "watched", "want_to_watch", "not_interested",
        "liked", "disliked", "rated",
    ]
    value: Optional[float] = None  # используется только для rated (1..5)


class InteractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    movie_id: int
    event_type: str
    value: Optional[float] = None
    ts: datetime


# ==============================
# USER MOVIE STATE
# ==============================
class MovieStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    movie_id: int
    status: Optional[str] = None
    rating: Optional[float] = None
    liked: bool = False
    disliked: bool = False
    updated_at: Optional[datetime] = None


# ==============================
# RECOMMENDATIONS
# ==============================
class SimilarOut(BaseModel):
    movie: MovieBrief
    score: float
    rank: int


class RecommendationOut(BaseModel):
    movie: MovieBrief
    score: float
    rank: int


# ==============================
# ALGORITHMS (dev)
# ==============================
class AlgorithmInfo(BaseModel):
    name: str
    display_name: str
    type: str            # 'baseline' | 'content' | 'collaborative'
    complexity: str
    available: bool


class CompareResult(BaseModel):
    movie_id: int
    k: int
    results: dict[str, dict]