"""
Бизнес-логика: работа с взаимодействиями, рекомендациями, кэшами алгоритмов.
"""
import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

# ── было: from models import ... / from schemas import ...
from backend.models import (
    Movie, Genre, Interaction, UserMovieState, User,
    SimilarMovie, RecommendationCache,
)
from backend.schemas import MovieBrief, SimilarOut, RecommendationOut

logger = logging.getLogger("movie_rec.services")

# ==============================
# CONSTANTS
# ==============================
VALID_EVENTS = {"watched", "want_to_watch", "not_interested", "liked", "disliked", "rated"}
STATUS_EVENTS = {"watched", "want_to_watch", "not_interested"}


# ==============================
# INTERACTIONS
# ==============================
def record_interaction(
    db: Session,
    user: User,
    movie_id: int,
    event_type: str,
    value: Optional[float] = None,
) -> Interaction:
    if event_type not in VALID_EVENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid event_type: {event_type}",
        )

    if event_type == "rated":
        if value is None:
            raise HTTPException(400, "rated event requires value 1..5")
        if not (1 <= value <= 5):
            raise HTTPException(400, "rating must be between 1 and 5")

    movie = db.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(404, "Movie not found")

    interaction = Interaction(
        user_id=user.id,
        movie_id=movie_id,
        event_type=event_type,
        value=value,
        ts=datetime.utcnow(),
    )
    db.add(interaction)

    state = (
        db.query(UserMovieState)
        .filter(UserMovieState.user_id == user.id, UserMovieState.movie_id == movie_id)
        .first()
    )
    if not state:
        state = UserMovieState(user_id=user.id, movie_id=movie_id)
        db.add(state)

    if event_type in STATUS_EVENTS:
        state.status = event_type
    elif event_type == "liked":
        state.liked = True
        state.disliked = False
    elif event_type == "disliked":
        state.disliked = True
        state.liked = False
    elif event_type == "rated":
        state.rating = value

    state.updated_at = datetime.utcnow()

    db.query(RecommendationCache).filter(
        RecommendationCache.user_id == user.id
    ).delete()

    db.commit()
    db.refresh(interaction)

    logger.info(
        f"Interaction recorded: user={user.id}, movie={movie_id}, "
        f"event={event_type}, value={value}"
    )
    return interaction


def delete_interaction(db: Session, user: User, movie_id: int, event_type: str) -> int:
    if event_type not in VALID_EVENTS:
        raise HTTPException(400, f"Invalid event_type: {event_type}")

    deleted = (
        db.query(Interaction)
        .filter(
            Interaction.user_id == user.id,
            Interaction.movie_id == movie_id,
            Interaction.event_type == event_type,
        )
        .delete(synchronize_session=False)
    )
    db.commit()

    if deleted == 0:
        raise HTTPException(404, "Interaction not found")

    db.query(RecommendationCache).filter(
        RecommendationCache.user_id == user.id
    ).delete()
    db.commit()

    return deleted


def get_user_state(db: Session, user: User, movie_id: int) -> Optional[UserMovieState]:
    return (
        db.query(UserMovieState)
        .filter(
            UserMovieState.user_id == user.id,
            UserMovieState.movie_id == movie_id,
        )
        .first()
    )


def get_user_movies_by_status(
    db: Session,
    user: User,
    status_value: str,
    limit: int = 200,
) -> list[Movie]:
    if status_value not in STATUS_EVENTS:
        raise HTTPException(400, f"Invalid status: {status_value}")

    states = (
        db.query(UserMovieState)
        .filter(
            UserMovieState.user_id == user.id,
            UserMovieState.status == status_value,
        )
        .order_by(desc(UserMovieState.updated_at))
        .limit(limit)
        .all()
    )
    if not states:
        return []

    movie_ids = [s.movie_id for s in states]
    movies = db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
    by_id = {m.id: m for m in movies}
    return [by_id[mid] for mid in movie_ids if mid in by_id]


# ==============================
# MOVIES
# ==============================
def get_movie_or_404(db: Session, movie_id: int) -> Movie:
    movie = db.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(404, "Movie not found")
    return movie


# ==============================
# SIMILAR MOVIES
# ==============================
def get_similar_movies(
    db: Session,
    movie_id: int,
    algorithm: str = "item_item",
    k: int = 10,
) -> list[SimilarOut]:
    source_movie = get_movie_or_404(db, movie_id)

    rows = (
        db.query(SimilarMovie)
        .filter(
            SimilarMovie.movie_id == movie_id,
            SimilarMovie.algorithm == algorithm,
        )
        .order_by(SimilarMovie.rank)
        .limit(k)
        .all()
    )
    if rows:
        return [
            SimilarOut(
                movie=MovieBrief.model_validate(r.similar_movie),
                score=r.score,
                rank=r.rank,
            )
            for r in rows
        ]

    try:
        from algorithms.registry import get_recommender
        rec = get_recommender(algorithm)
        similar_pairs = rec.similar_items(movie_id, k)

        out = []
        for rank, (sim_id, score) in enumerate(similar_pairs, 1):
            m = db.query(Movie).filter(Movie.id == sim_id).first()
            if m:
                out.append(SimilarOut(
                    movie=MovieBrief.model_validate(m),
                    score=float(score),
                    rank=rank,
                ))
        if out:
            return out
    except ImportError:
        logger.debug(f"algorithms/ package not available for {algorithm}")
    except Exception as e:
        logger.warning(f"Algorithm {algorithm} failed: {e}")

    return _similar_by_genres(db, source_movie, k)


def _similar_by_genres(db: Session, movie: Movie, k: int) -> list[SimilarOut]:
    genre_ids = [g.id for g in movie.genres]
    if not genre_ids:
        return []

    candidates = (
        db.query(Movie)
        .join(Movie.genres)
        .filter(Genre.id.in_(genre_ids), Movie.id != movie.id)
        .group_by(Movie.id)
        .order_by(desc(func.count(Genre.id)), desc(Movie.popularity))
        .limit(k)
        .all()
    )
    return [
        SimilarOut(movie=MovieBrief.model_validate(m), score=0.5, rank=i + 1)
        for i, m in enumerate(candidates)
    ]


# ==============================
# RECOMMENDATIONS
# ==============================
def get_recommendations(
    db: Session,
    user: User,
    algorithm: str = "popularity",
    k: int = 20,
) -> list[RecommendationOut]:
    cached = (
        db.query(RecommendationCache)
        .filter(
            RecommendationCache.user_id == user.id,
            RecommendationCache.algorithm == algorithm,
        )
        .first()
    )
    if cached and cached.movie_ids:
        movies = db.query(Movie).filter(Movie.id.in_(cached.movie_ids)).all()
        by_id = {m.id: m for m in movies}
        out = []
        for rank, (mid, score) in enumerate(zip(cached.movie_ids, cached.scores), 1):
            if mid in by_id:
                out.append(RecommendationOut(
                    movie=MovieBrief.model_validate(by_id[mid]),
                    score=float(score),
                    rank=rank,
                ))
        if out:
            return out[:k]

    try:
        from algorithms.registry import get_recommender
        rec = get_recommender(algorithm)
        recs = rec.recommend_for_user(user.id, k)

        out = []
        for rank, (mid, score) in enumerate(recs, 1):
            m = db.query(Movie).filter(Movie.id == mid).first()
            if m:
                out.append(RecommendationOut(
                    movie=MovieBrief.model_validate(m),
                    score=float(score),
                    rank=rank,
                ))
        if out:
            return out
    except ImportError:
        logger.debug("algorithms/ package not available")
    except Exception as e:
        logger.warning(f"Recommendation algorithm {algorithm} failed: {e}")

    return _popular_fallback(db, user, k)


def _popular_fallback(db: Session, user: User, k: int) -> list[RecommendationOut]:
    watched_ids = {
        row[0] for row in
        db.query(UserMovieState.movie_id)
        .filter(
            UserMovieState.user_id == user.id,
            UserMovieState.status == "watched",
        )
        .all()
    }

    query = db.query(Movie).order_by(desc(Movie.popularity))
    if watched_ids:
        query = query.filter(~Movie.id.in_(watched_ids))

    popular = query.limit(k).all()
    return [
        RecommendationOut(
            movie=MovieBrief.model_validate(m),
            score=float(m.popularity or 0),
            rank=i + 1,
        )
        for i, m in enumerate(popular)
    ]


# ==============================
# ALGORITHMS (DEV)
# ==============================
def compare_algorithms(db: Session, movie_id: int, k: int = 10) -> dict:
    get_movie_or_404(db, movie_id)

    algos_to_test = ["popularity", "jaccard", "tfidf", "item_item", "mf"]
    results = {}
    first_set = None

    for algo in algos_to_test:
        t0 = time.perf_counter()
        try:
            rows = (
                db.query(SimilarMovie)
                .filter(
                    SimilarMovie.movie_id == movie_id,
                    SimilarMovie.algorithm == algo,
                )
                .order_by(SimilarMovie.rank)
                .limit(k)
                .all()
            )
            items = [r.similar_movie_id for r in rows]
            elapsed_ms = (time.perf_counter() - t0) * 1000

            if not items:
                try:
                    from algorithms.registry import get_recommender
                    rec = get_recommender(algo)
                    t0 = time.perf_counter()
                    pairs = rec.similar_items(movie_id, k)
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    items = [mid for mid, _ in pairs]
                except Exception:
                    continue

            overlap = None
            if first_set is not None:
                union = set(items) | first_set
                overlap = (
                    len(set(items) & first_set) / len(union)
                    if union else 0.0
                )
            else:
                first_set = set(items)

            results[algo] = {
                "time_ms": round(elapsed_ms, 2),
                "items": items,
                "count": len(items),
                "overlap": round(overlap, 3) if overlap is not None else None,
            }
        except Exception as e:
            results[algo] = {"error": str(e)}

    return {"movie_id": movie_id, "k": k, "results": results}


def rebuild_algorithm_cache(db: Session, algorithm: str, max_movies: int = 100) -> dict:
    try:
        from algorithms.registry import get_recommender
        from algorithms.dataset import load_dataset
    except ImportError as e:
        raise HTTPException(
            status_code=501,
            detail=f"algorithms/ package not available: {e}",
        )

    try:
        rec = get_recommender(algorithm)
        dataset = load_dataset()
        rec.fit(dataset)

        movie_ids = list(dataset.movie_index.keys())[:max_movies]
        count = 0

        for mid in movie_ids:
            similar = rec.similar_items(mid, k=20)

            db.query(SimilarMovie).filter(
                SimilarMovie.movie_id == mid,
                SimilarMovie.algorithm == algorithm,
            ).delete(synchronize_session=False)

            for rank, (sim_id, score) in enumerate(similar, 1):
                db.add(SimilarMovie(
                    movie_id=mid,
                    algorithm=algorithm,
                    similar_movie_id=sim_id,
                    score=float(score),
                    rank=rank,
                    generated_at=datetime.utcnow(),
                ))
            count += 1

        db.commit()
        logger.info(f"Rebuilt cache for {algorithm}: {count} movies")

        return {
            "status": "ok",
            "algorithm": algorithm,
            "movies_processed": count,
            "total_available": len(dataset.movie_index),
        }

    except Exception as e:
        db.rollback()
        logger.exception(f"Rebuild failed for {algorithm}")
        raise HTTPException(500, f"Rebuild failed: {e}")