#!/usr/bin/env python3
"""
seed.py — загружает MovieLens ml-latest-small в SQLite.

Usage:
    python scripts/seed.py                    # загрузить (если БД пустая)
    python scripts/seed.py --reset            # дропнуть всё и залить заново
    python scripts/seed.py --data data/raw/ml-latest-small
    python scripts/seed.py --demo             # 500 фильмов, 100 юзеров, 10k оценок
"""
import os
import sys
import csv
import argparse
import logging
import re
from datetime import datetime

# --- sys.path: чтобы `from backend.db import ...` работал из любого места
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from passlib.context import CryptContext
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from backend.db import engine, SessionLocal
from backend.models import (
    Base, Movie, Genre, User, Interaction, UserMovieState,
)

logger = logging.getLogger("seed")

# ==============================
# CONSTANTS
# ==============================
DEFAULT_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "raw", "ml-latest-small",
)

EXPECTED_FILES = ["movies.csv", "ratings.csv", "links.csv"]

DEMO_PASSWORD = "demo123"
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Хеш считается один раз — bcrypt медленный, не хотим 100 раз его гонять.
_DEMO_HASH = None


def get_demo_hash() -> str:
    global _DEMO_HASH
    if _DEMO_HASH is None:
        _DEMO_HASH = _pwd_ctx.hash(DEMO_PASSWORD)
    return _DEMO_HASH


# ==============================
# HELPERS
# ==============================
def parse_title_year(raw_title: str):
    """
    'Toy Story (1995)' -> ('Toy Story', 1995)
    'Matrix, The (1999)' -> ('Matrix, The', 1999)
    """
    match = re.search(r"\((\d{4})\)$", raw_title)
    if match:
        return raw_title[:match.start()].strip(), int(match.group(1))
    return raw_title.strip(), None


def setup_logging(verbose: bool = False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def check_data_dir(data_dir: str) -> None:
    if not os.path.isdir(data_dir):
        logger.error(f"Data directory not found: {data_dir}")
        logger.info("Download ml-latest-small from https://grouplens.org/datasets/movielens/")
        logger.info(f"Unzip to: {data_dir}")
        sys.exit(1)

    missing = [f for f in EXPECTED_FILES if not os.path.exists(os.path.join(data_dir, f))]
    if missing:
        logger.warning(f"Missing files: {missing}")
    else:
        logger.info(f"All expected files found in {data_dir}")


# ==============================
# SEEDER
# ==============================
class Seeder:
    def __init__(self, data_dir: str, reset: bool = False, demo: bool = False):
        self.data_dir = data_dir
        self.reset = reset
        self.demo = demo
        self.db = SessionLocal()

        self.genre_cache: dict[str, Genre] = {}
        self.allowed_movie_ids: set[int] = set()
        self.allowed_user_ids: set[int] = set()

        self.movie_count = 0
        self.user_count = 0
        self.interaction_count = 0

    def run(self):
        try:
            self._create_tables()

            if self.reset:
                self._drop_all()
                self._create_tables()
            else:
                existing = self.db.query(Movie).count()
                if existing > 0:
                    logger.warning(
                        f"Database already has {existing} movies. "
                        f"Use --reset to re-seed. Skipping."
                    )
                    return

            self._seed_genres_and_movies()
            self._seed_links()
            self._seed_users_and_ratings()

            self.db.commit()
            self._print_summary()

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.exception(f"Database error: {e}")
            raise
        except Exception as e:
            self.db.rollback()
            logger.exception(f"Unexpected error: {e}")
            raise
        finally:
            self.db.close()

    def _create_tables(self):
        logger.info("Creating tables...")
        Base.metadata.create_all(bind=engine)

    def _drop_all(self):
        logger.warning("Dropping all tables (--reset)...")
        Base.metadata.drop_all(bind=engine)

    # --------------------
    # MOVIES + GENRES
    # --------------------
    def _seed_genres_and_movies(self):
        path = os.path.join(self.data_dir, "movies.csv")
        logger.info(f"Reading movies from {path}")

        all_genres: set[str] = set()
        rows: list[dict] = []

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
                genres_str = row.get("genres", "")
                if genres_str:
                    for g in genres_str.split("|"):
                        all_genres.add(g.strip())

        # Жанры
        for genre_name in sorted(all_genres):
            genre = Genre(name=genre_name)
            self.db.add(genre)
            self.genre_cache[genre_name] = genre
        self.db.flush()
        logger.info(f"Created {len(self.genre_cache)} genres")

        # Фильмы
        limit = 500 if self.demo else len(rows)
        for i, row in enumerate(rows):
            if i >= limit:
                break

            title_raw = row["title"]
            title, year = parse_title_year(title_raw)
            movie_id = int(row["movieId"])

            movie = Movie(
                id=movie_id,
                title=title,
                original_title=title_raw,
                year=year,
            )

            genres_str = row.get("genres", "")
            if genres_str:
                for g in genres_str.split("|"):
                    g = g.strip()
                    if g in self.genre_cache:
                        movie.genres.append(self.genre_cache[g])

            self.db.add(movie)
            self.allowed_movie_ids.add(movie_id)
            self.movie_count += 1

            if self.movie_count % 200 == 0:
                self.db.flush()
                logger.info(f"  ... {self.movie_count} movies")

        self.db.flush()
        logger.info(f"Created {self.movie_count} movies")

    # --------------------
    # LINKS
    # --------------------
    def _seed_links(self):
        path = os.path.join(self.data_dir, "links.csv")
        if not os.path.exists(path):
            logger.info("links.csv not found, skipping")
            return

        logger.info(f"Reading links from {path}")
        updated = 0

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                movie_id = int(row["movieId"])
                if movie_id not in self.allowed_movie_ids:
                    continue

                tmdb_id = row.get("tmdbId", "").strip()
                if not tmdb_id:
                    continue

                movie = self.db.query(Movie).filter(Movie.id == movie_id).first()
                if movie:
                    movie.tmdb_id = int(tmdb_id)
                    updated += 1

                if updated % 500 == 0 and updated > 0:
                    self.db.flush()

        logger.info(f"Updated tmdb_id for {updated} movies")

    # --------------------
    # USERS + RATINGS
    # --------------------
    def _seed_users_and_ratings(self):
        path = os.path.join(self.data_dir, "ratings.csv")
        logger.info(f"Reading ratings from {path}")

        user_ids: set[int] = set()
        ratings_rows: list[dict] = []

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                user_ids.add(int(row["userId"]))
                ratings_rows.append(row)

        # Юзеры
        limit_users = 100 if self.demo else len(user_ids)
        selected_users = sorted(user_ids)[:limit_users]
        demo_hash = get_demo_hash()

        for uid in selected_users:
            user = User(
                id=uid,
                username=f"user_{uid}",
                password_hash=demo_hash,
                created_at=datetime.utcnow(),
            )
            self.db.add(user)
            self.allowed_user_ids.add(uid)
            self.user_count += 1

        self.db.flush()
        logger.info(
            f"Created {self.user_count} users (password for all: '{DEMO_PASSWORD}')"
        )

        # Ratings → interactions + state
        limit_ratings = 10000 if self.demo else len(ratings_rows)
        processed = 0
        seen_pairs: set[tuple[int, int]] = set()

        for row in ratings_rows:
            if processed >= limit_ratings:
                break

            user_id = int(row["userId"])
            movie_id = int(row["movieId"])

            # В демо-режиме — только разрешённые
            if user_id not in self.allowed_user_ids:
                continue
            if movie_id not in self.allowed_movie_ids:
                continue

            rating = float(row["rating"])
            timestamp = int(row["timestamp"])
            dt = datetime.fromtimestamp(timestamp)

            self.db.add(Interaction(
                user_id=user_id,
                movie_id=movie_id,
                event_type="rated",
                value=rating,
                ts=dt,
            ))
            self.interaction_count += 1

            pair = (user_id, movie_id)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                self.db.add(UserMovieState(
                    user_id=user_id,
                    movie_id=movie_id,
                    status="watched",
                    rating=rating,
                    liked=rating >= 4.0,
                    disliked=rating <= 2.0,
                    updated_at=dt,
                ))

            processed += 1
            if processed % 10000 == 0:
                self.db.flush()
                logger.info(f"  ... {processed} ratings processed")

        logger.info(f"Created {self.interaction_count} interactions")

    # --------------------
    # SUMMARY
    # --------------------
    def _print_summary(self):
        movies = self.db.query(func.count(Movie.id)).scalar()
        users = self.db.query(func.count(User.id)).scalar()
        interactions = self.db.query(func.count(Interaction.id)).scalar()
        states = self.db.query(func.count(UserMovieState.user_id)).scalar()
        genres = self.db.query(func.count(Genre.id)).scalar()

        print("\n" + "=" * 50)
        print("SEED COMPLETE")
        print("=" * 50)
        print(f"  Movies:       {movies}")
        print(f"  Genres:       {genres}")
        print(f"  Users:        {users}")
        print(f"  Interactions: {interactions}")
        print(f"  User states:  {states}")
        print("=" * 50)
        print(f"  Password for seeded users: '{DEMO_PASSWORD}'")
        print("=" * 50)


# ==============================
# CLI
# ==============================
def main():
    parser = argparse.ArgumentParser(description="Seed MovieLens data into SQLite")
    parser.add_argument(
        "--data", type=str, default=DEFAULT_DATA_DIR,
        help=f"Path to ml-latest-small directory (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Drop all tables and re-seed from scratch",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Quick demo: 500 movies, 100 users, 10k ratings",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)
    check_data_dir(args.data)

    Seeder(args.data, reset=args.reset, demo=args.demo).run()


if __name__ == "__main__":
    main()