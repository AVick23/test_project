#!/usr/bin/env python3
"""
build_cache.py — прогоняет алгоритмы и пишет результаты в БД.

Usage:
    python scripts/build_cache.py                     # все алгоритмы
    python scripts/build_cache.py --algo=item_item    # один алгоритм
    python scripts/build_cache.py --algo=popularity --bench
    python scripts/build_cache.py --limit=100         # только 100 фильмов
    python scripts/build_cache.py --k=20              # top-20
"""
import os
import sys
import time
import argparse
import logging
from datetime import datetime
from collections import defaultdict

# --- sys.path: чтобы `from backend.db import ...` и `from algorithms...` работали
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backend.db import SessionLocal
from backend.models import (
    Movie, User, SimilarMovie, RecommendationCache, UserMovieState,
)

logger = logging.getLogger("build_cache")

# ==============================
# CONFIG
# ==============================
ALL_ALGORITHMS = ["popularity", "jaccard", "tfidf", "item_item", "mf"]
DEFAULT_K = 50
DEFAULT_SIMILAR_LIMIT = 500
DEFAULT_USER_LIMIT = 100


# ==============================
# DATASET LOADER
# ==============================
def load_dataset():
    """
    Пытается загрузить Dataset из algorithms.dataset.
    Если модуль ещё не реализован — использует локальный fallback.
    """
    try:
        from algorithms.dataset import load_dataset as _load
        logger.info("Loading dataset via algorithms.dataset...")
        return _load()
    except (ImportError, ModuleNotFoundError):
        logger.warning("algorithms.dataset not available — using fallback loader")
        return _fallback_dataset()


def _fallback_dataset():
    """
    Минимальный Dataset прямо из БД.
    Используется, пока algorithms/dataset.py не написан.
    """
    from scipy.sparse import csr_matrix
    import numpy as np

    db = SessionLocal()
    try:
        users = db.query(User).all()
        user_ids = [u.id for u in users]

        movies = db.query(Movie).all()
        movie_ids = [m.id for m in movies]

        states = (
            db.query(UserMovieState)
            .filter(UserMovieState.rating.isnot(None))
            .all()
        )

        user_index = {uid: i for i, uid in enumerate(user_ids)}
        movie_index = {mid: i for i, mid in enumerate(movie_ids)}

        rows, cols, vals = [], [], []
        user_items: dict[int, set[int]] = defaultdict(set)
        item_users: dict[int, set[int]] = defaultdict(set)

        for s in states:
            if s.user_id not in user_index or s.movie_id not in movie_index:
                continue
            rows.append(user_index[s.user_id])
            cols.append(movie_index[s.movie_id])
            vals.append(s.rating or 1.0)
            user_items[s.user_id].add(s.movie_id)
            item_users[s.movie_id].add(s.user_id)

        R = csr_matrix(
            (vals, (rows, cols)),
            shape=(len(user_ids), len(movie_ids)),
            dtype=np.float32,
        )

        movie_genres = {m.id: {g.id for g in m.genres} for m in movies}
        titles = {m.id: m.title for m in movies}

    finally:
        db.close()

    class SimpleDataset:
        pass

    ds = SimpleDataset()
    ds.R = R
    ds.user_ids = user_ids
    ds.movie_ids = movie_ids
    ds.user_index = user_index
    ds.movie_index = movie_index
    ds.user_items = dict(user_items)
    ds.item_users = dict(item_users)
    ds.movie_genres = movie_genres
    ds.titles = titles
    return ds


# ==============================
# CACHE BUILDER
# ==============================
class CacheBuilder:
    def __init__(self, algorithm: str, k: int, similar_limit: int, user_limit: int):
        self.algorithm = algorithm
        self.k = k
        self.similar_limit = similar_limit
        self.user_limit = user_limit
        self.db = SessionLocal()
        self.dataset = None
        self.recommender = None
        self.stats = {
            "similar_computed": 0,
            "recs_computed": 0,
            "errors": 0,
            "time_fit": 0.0,
            "time_similar": 0.0,
            "time_recs": 0.0,
        }

    def run(self) -> dict:
        logger.info(f"Starting build_cache for algorithm: {self.algorithm}")
        t_total = time.perf_counter()

        try:
            self._load_dataset()
            self._load_recommender()
            self._fit()
            self._build_similar()
            self._build_recommendations()
            self.db.commit()

            elapsed = time.perf_counter() - t_total
            self._print_summary(elapsed)
            return self.stats

        except (ImportError, ModuleNotFoundError) as e:
            logger.error(f"algorithms/ package not available: {e}")
            logger.info("Implement algorithms/ to enable cache building")
            return {"error": str(e)}

        except Exception as e:
            self.db.rollback()
            logger.exception(f"Build failed: {e}")
            raise

        finally:
            self.db.close()

    # --------------------
    # LOAD
    # --------------------
    def _load_dataset(self):
        self.dataset = load_dataset()
        logger.info(
            f"Dataset loaded: {len(self.dataset.user_ids)} users, "
            f"{len(self.dataset.movie_ids)} movies, "
            f"nnz={self.dataset.R.nnz}"
        )

    def _load_recommender(self):
        from algorithms.registry import get_recommender
        self.recommender = get_recommender(self.algorithm)
        logger.info(f"Recommender loaded: {self.algorithm}")

    # --------------------
    # FIT
    # --------------------
    def _fit(self):
        t0 = time.perf_counter()
        self.recommender.fit(self.dataset)
        self.stats["time_fit"] = time.perf_counter() - t0
        logger.info(f"Fit completed in {self.stats['time_fit']:.2f}s")

    # --------------------
    # SIMILAR MOVIES
    # --------------------
    def _build_similar(self):
        logger.info(f"Computing similar movies (limit={self.similar_limit})...")
        t0 = time.perf_counter()

        movie_ids = self.dataset.movie_ids[: self.similar_limit]
        processed = 0
        batch_size = 50

        for movie_id in movie_ids:
            try:
                similar = self.recommender.similar_items(movie_id, self.k)

                self.db.query(SimilarMovie).filter(
                    SimilarMovie.movie_id == movie_id,
                    SimilarMovie.algorithm == self.algorithm,
                ).delete(synchronize_session=False)

                for rank, (sim_id, score) in enumerate(similar, 1):
                    self.db.add(SimilarMovie(
                        movie_id=movie_id,
                        algorithm=self.algorithm,
                        similar_movie_id=sim_id,
                        score=float(score),
                        rank=rank,
                        generated_at=datetime.utcnow(),
                    ))

                processed += 1
                self.stats["similar_computed"] += 1

                if processed % batch_size == 0:
                    self.db.flush()
                    logger.info(f"  ... {processed}/{len(movie_ids)} similar")

            except Exception as e:
                self.stats["errors"] += 1
                logger.debug(f"Error for movie {movie_id}: {e}")

        self.stats["time_similar"] = time.perf_counter() - t0
        logger.info(
            f"Similar done: {self.stats['similar_computed']} in "
            f"{self.stats['time_similar']:.2f}s"
        )

    # --------------------
    # RECOMMENDATIONS
    # --------------------
    def _build_recommendations(self):
        logger.info(f"Computing user recommendations (limit={self.user_limit})...")
        t0 = time.perf_counter()

        user_ids = self.dataset.user_ids[: self.user_limit]
        processed = 0

        for user_id in user_ids:
            try:
                recs = self.recommender.recommend_for_user(user_id, self.k)
                if not recs:
                    continue

                movie_ids_list = [mid for mid, _ in recs]
                scores_list = [float(score) for _, score in recs]

                self.db.query(RecommendationCache).filter(
                    RecommendationCache.user_id == user_id,
                    RecommendationCache.algorithm == self.algorithm,
                ).delete(synchronize_session=False)

                self.db.add(RecommendationCache(
                    user_id=user_id,
                    algorithm=self.algorithm,
                    movie_ids=movie_ids_list,
                    scores=scores_list,
                    generated_at=datetime.utcnow(),
                ))

                processed += 1
                self.stats["recs_computed"] += 1

            except Exception as e:
                self.stats["errors"] += 1
                logger.debug(f"Error for user {user_id}: {e}")

        self.stats["time_recs"] = time.perf_counter() - t0
        logger.info(
            f"Recs done: {self.stats['recs_computed']} in "
            f"{self.stats['time_recs']:.2f}s"
        )

    # --------------------
    # SUMMARY
    # --------------------
    def _print_summary(self, total_time: float):
        print("\n" + "=" * 55)
        print(f"CACHE BUILD COMPLETE — {self.algorithm}")
        print("=" * 55)
        print(f"  Fit time:          {self.stats['time_fit']:.2f}s")
        print(f"  Similar time:      {self.stats['time_similar']:.2f}s")
        print(f"  Recs time:         {self.stats['time_recs']:.2f}s")
        print(f"  Total time:        {total_time:.2f}s")
        print("-" * 55)
        print(f"  Similar computed:  {self.stats['similar_computed']}")
        print(f"  Recs computed:     {self.stats['recs_computed']}")
        print(f"  Errors:            {self.stats['errors']}")
        print("=" * 55)


# ==============================
# BENCHMARK
# ==============================
def run_benchmark(algorithm: str, k: int = 10):
    try:
        import psutil
        has_psutil = True
    except ImportError:
        has_psutil = False

    print(f"\n[BENCHMARK] {algorithm}")
    print("-" * 40)

    process = psutil.Process() if has_psutil else None
    mem_before = process.memory_info().rss / 1024 / 1024 if process else 0

    t0 = time.perf_counter()
    dataset = load_dataset()
    t_load = time.perf_counter() - t0

    from algorithms.registry import get_recommender
    rec = get_recommender(algorithm)

    t0 = time.perf_counter()
    rec.fit(dataset)
    t_fit = time.perf_counter() - t0

    t0 = time.perf_counter()
    for mid in dataset.movie_ids[:10]:
        rec.similar_items(mid, k)
    t_similar = (time.perf_counter() - t0) / 10

    mem_after = process.memory_info().rss / 1024 / 1024 if process else 0

    print(f"  Load time:      {t_load:.3f}s")
    print(f"  Fit time:       {t_fit:.3f}s")
    print(f"  Similar (avg):  {t_similar * 1000:.1f}ms")
    if has_psutil:
        print(f"  Memory delta:   {mem_after - mem_before:+.1f} MB")
    print()


# ==============================
# CLI
# ==============================
def main():
    parser = argparse.ArgumentParser(description="Build recommendation cache")
    parser.add_argument(
        "--algo", type=str, choices=ALL_ALGORITHMS + ["all"], default="all",
    )
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--limit", type=int, default=DEFAULT_SIMILAR_LIMIT)
    parser.add_argument("--users", type=int, default=DEFAULT_USER_LIMIT)
    parser.add_argument("--bench", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.bench:
        algos = ALL_ALGORITHMS if args.algo == "all" else [args.algo]
        for algo in algos:
            try:
                run_benchmark(algo, args.k)
            except ImportError as e:
                print(f"  SKIP {algo}: {e}")
            except Exception as e:
                print(f"  ERROR {algo}: {e}")
        return

    algos = ALL_ALGORITHMS if args.algo == "all" else [args.algo]
    results = {}

    for algo in algos:
        logger.info(f"\n{'=' * 50}\nProcessing: {algo}\n{'=' * 50}")
        try:
            builder = CacheBuilder(algo, args.k, args.limit, args.users)
            results[algo] = builder.run()
        except ImportError as e:
            logger.warning(f"SKIP {algo}: algorithms/ not available")
            results[algo] = {"skipped": str(e)}
        except Exception as e:
            logger.error(f"FAILED {algo}: {e}")
            results[algo] = {"error": str(e)}

    print("\n" + "=" * 55)
    print("ALL ALGORITHMS SUMMARY")
    print("=" * 55)
    for algo, res in results.items():
        if "error" in res or "skipped" in res:
            status = res.get("error") or res.get("skipped")
            print(f"  {algo:15s} → SKIP/ERROR: {status}")
        else:
            total_time = res["time_fit"] + res["time_similar"] + res["time_recs"]
            print(
                f"  {algo:15s} → similar={res['similar_computed']}, "
                f"recs={res['recs_computed']}, time={total_time:.1f}s"
            )
    print("=" * 55)


if __name__ == "__main__":
    main()