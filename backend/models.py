"""
SQLAlchemy ORM модели для Movie-Rec.
1:1 отражают схему из design doc.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean,
    DateTime, ForeignKey, Index, UniqueConstraint,
    Table, Enum as SAEnum, JSON,
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


# ==============================
# MOVIES
# ==============================
class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True)
    tmdb_id = Column(Integer, unique=True, nullable=True)
    title = Column(String(512), nullable=False)
    original_title = Column(String(512), nullable=True)
    year = Column(Integer, nullable=True, index=True)
    runtime = Column(Integer, nullable=True)
    overview = Column(Text, nullable=True)
    poster_path = Column(String(256), nullable=True)
    original_language = Column(String(10), nullable=True)
    popularity = Column(Float, default=0.0, index=True)
    vote_average = Column(Float, default=0.0)
    vote_count = Column(Integer, default=0)

    # relationships
    genres = relationship(
        "Genre",
        secondary="movie_genres",
        back_populates="movies",
        lazy="selectin",
    )
    keywords = relationship(
        "Keyword",
        secondary="movie_keywords",
        back_populates="movies",
        lazy="selectin",
    )
    credits = relationship("MovieCredit", back_populates="movie", lazy="selectin")
    states = relationship("UserMovieState", back_populates="movie", lazy="dynamic")

    __table_args__ = (
        Index("idx_movies_year", "year"),
        Index("idx_movies_popularity", "popularity"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tmdb_id": self.tmdb_id,
            "title": self.title,
            "original_title": self.original_title,
            "year": self.year,
            "runtime": self.runtime,
            "overview": self.overview,
            "poster_path": self.poster_path,
            "original_language": self.original_language,
            "popularity": self.popularity,
            "vote_average": self.vote_average,
            "vote_count": self.vote_count,
            "genres": [g.name for g in self.genres],
        }


class Genre(Base):
    __tablename__ = "genres"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)

    movies = relationship("Movie", secondary="movie_genres", back_populates="genres")


movie_genres = Table(
    "movie_genres",
    Base.metadata,
    Column("movie_id", Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", Integer, ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
    Index("idx_movie_genres_genre", "genre_id"),
)


class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True, nullable=False)

    movies = relationship("Movie", secondary="movie_keywords", back_populates="keywords")


movie_keywords = Table(
    "movie_keywords",
    Base.metadata,
    Column("movie_id", Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("keyword_id", Integer, ForeignKey("keywords.id", ondelete="CASCADE"), primary_key=True),
)


class Person(Base):
    __tablename__ = "people"

    id = Column(Integer, primary_key=True)
    name = Column(String(256), nullable=False)
    tmdb_id = Column(Integer, unique=True, nullable=True)

    credits = relationship("MovieCredit", back_populates="person", lazy="dynamic")


class MovieCredit(Base):
    __tablename__ = "movie_credits"

    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    person_id = Column(Integer, ForeignKey("people.id", ondelete="CASCADE"), primary_key=True)
    role = Column(String(32), primary_key=True)  # 'actor' | 'director' | 'writer'
    billing_order = Column(Integer, nullable=True)

    movie = relationship("Movie", back_populates="credits")
    person = relationship("Person", back_populates="credits")


# ==============================
# USERS
# ==============================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(256), unique=True, nullable=True)
    password_hash = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    interactions = relationship("Interaction", back_populates="user", lazy="dynamic")
    states = relationship("UserMovieState", back_populates="user", lazy="dynamic")


class EventType(str, enum.Enum):
    watched = "watched"
    want_to_watch = "want_to_watch"
    not_interested = "not_interested"
    liked = "liked"
    disliked = "disliked"
    rated = "rated"


class Interaction(Base):
    """Append-only лог всех действий пользователя."""
    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(32), nullable=False)
    value = Column(Float, nullable=True)  # для rated: 1..5
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="interactions")
    movie = relationship("Movie")

    __table_args__ = (
        Index("idx_int_user_ts", "user_id", "ts"),
        Index("idx_int_movie_ts", "movie_id", "ts"),
    )


class UserMovieState(Base):
    """Текущее состояние user↔movie. Обновляется при каждом interaction."""
    __tablename__ = "user_movie_state"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    status = Column(String(32), nullable=True)      # watched | want_to_watch | not_interested | NULL
    rating = Column(Float, nullable=True)           # 1..5 | NULL
    liked = Column(Boolean, default=False)
    disliked = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="states")
    movie = relationship("Movie", back_populates="states")


# ==============================
# CACHES (заполняются scripts/build_cache.py)
# ==============================
class SimilarMovie(Base):
    """Кэш похожих фильмов от алгоритмов."""
    __tablename__ = "similar_movies"

    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    algorithm = Column(String(64), primary_key=True)
    similar_movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    score = Column(Float, nullable=False)
    rank = Column(Integer, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)

    movie = relationship("Movie", foreign_keys=[movie_id])
    similar_movie = relationship("Movie", foreign_keys=[similar_movie_id], lazy="selectin")

    __table_args__ = (
        Index("idx_similar_rank", "movie_id", "algorithm", "rank"),
    )


class RecommendationCache(Base):
    """Персональные рекомендации."""
    __tablename__ = "rec_cache"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    algorithm = Column(String(64), primary_key=True)
    movie_ids = Column(JSON, nullable=False)   # [1, 5, 42, ...]
    scores = Column(JSON, nullable=False)      # [0.9, 0.8, ...]
    generated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")