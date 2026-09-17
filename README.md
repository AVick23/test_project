# 🎬 Movie-Rec

Учебный проект: **трекер фильмов с рекомендательной системой**.

Backend, frontend, база данных и API — уже готовы и работают.
**Твоя работа — писать алгоритмы рекомендаций в папке `algorithms/`.**

> **Проект создан как песочница для отработки алгоритмов и структур данных**
> на реальных данных (MovieLens ml-latest-small: 9742 фильма, 610 пользователей,
> 100 836 оценок). Всё, что ты напишешь в `algorithms/`, сразу попадает в живое
> веб-приложение и меняет рекомендации в браузере.

---

## 📖 О проекте

Movie-Rec — это **Netflix на минималках** без онлайн-просмотра:

- Каталог фильмов с поиском, фильтрами и жанрами
- Регистрация и вход по JWT
- Отметки: `смотрел`, `хочу посмотреть`, `не интересно`, `лайк`, `дизлайк`, `оценка 1–5`
- Похожие фильмы для каждого фильма
- Персональные рекомендации для каждого пользователя
- Страница сравнения алгоритмов (`/algorithms`)

**Что делает проект особенным для обучения:**

1. **Алгоритмы изолированы.** Backend не знает, как работает Jaccard или Item-Item CF.
   Он просто вызывает три функции у модуля из `algorithms/`.
2. **Реальные данные.** 100 836 оценок — достаточно, чтобы увидеть разницу между
   «наивной» и «оптимизированной» реализацией (в 1000 раз по скорости).
3. **Мгновенная обратная связь.** Написал алгоритм — перестроил кэш — увидел
   изменившиеся рекомендации в браузере.
4. **Метрики.** Precision@k, Recall@k, NDCG@k — сравнивай алгоритмы объективно,
   а не «мне кажется, этот лучше».

---

## 🎯 Для кого этот проект

- **Студенты** дисциплин «Основы алгоритмизации и программирования»,
  «Структуры и алгоритмы обработки данных», «Рекомендательные системы».
- **Преподаватели** — как готовый каркас для практических работ.
- **Все, кто учится писать алгоритмы** и хочет видеть результат своей работы
  в работающем приложении, а не в консольных `print()`.

**Методические указания** по шагам лежат в папке
[`methodological_guides/`](methodological_guides/). Начинай с них.

---

## 🏗️ Что внутри проекта

```
test_project/
├── algorithms/          ⬅️  ЗДЕСЬ ПИШЕМ АЛГОРИТМЫ
│   ├── __init__.py
│   ├── registry.py      реестр алгоритмов: имя → модуль
│   ├── dataset.py       загрузка данных из БД в структуры для алгоритмов
│   ├── topk.py          три способа получить top-K
│   ├── metrics.py       Precision@k, Recall@k, NDCG@k
│   ├── popularity.py    baseline: самое популярное
│   ├── content.py       Jaccard + TF-IDF (content-based)
│   ├── item_item.py     Item-Item collaborative filtering
│   └── mf.py            Matrix factorization через SGD
│
├── backend/             ✅  ГОТОВ. НЕ ТРОГАЕМ.
│   ├── main.py          FastAPI: все роуты
│   ├── models.py        SQLAlchemy: таблицы
│   ├── schemas.py       Pydantic: схемы API
│   ├── db.py            подключение к SQLite
│   ├── auth.py          JWT + bcrypt
│   └── services.py      бизнес-логика (вызывает algorithms/)
│
├── frontend/            ✅  ГОТОВ. НЕ ТРОГАЕМ.
│   ├── index.html       SPA с hash-роутингом
│   ├── app.js           API-клиент + рендер
│   └── style.css        glassmorphism + Apple-style
│
├── scripts/             ✅  ГОТОВ. Используем как есть.
│   ├── seed.py          загрузка MovieLens в SQLite
│   └── build_cache.py   прогон алгоритмов и запись кэша
│
├── data/                📦  Данные и БД
│   ├── movies.db        SQLite (создаётся seed.py)
│   └── raw/
│       └── ml-latest-small/   ← сюда кладём CSV от MovieLens
│
├── methodological_guides/   📚  Учебные материалы
│   ├── 01_intro.md
│   ├── 02_registry.md
│   ├── 03_dataset.md
│   └── ...
│
├── requirements.txt
└── README.md            ← ты здесь
```

**Ключевое правило курса:**

> Backend, frontend, `seed.py`, `build_cache.py` — **готовы**.
> Ничего в них трогать не нужно.
> Твоя работа — только в `algorithms/`.

---

## 🛠️ Стек технологий

**Backend:**
- Python 3.11 / 3.12
- FastAPI 0.115 — REST API
- SQLAlchemy 2.0 — ORM
- Pydantic 2.9 — валидация
- SQLite + WAL — БД (одного файла хватает)
- passlib + bcrypt — хеширование паролей
- python-jose — JWT

**Алгоритмы:**
- numpy — векторы и матрицы
- scipy — разреженные матрицы (`csr_matrix`)
- scikit-learn — TF-IDF (опционально)

**Frontend:**
- Чистый HTML / CSS / JS — без сборки
- Glassmorphism, тёмная тема

---

## 🚀 Быстрый старт

### 1. Клонировать и подготовить окружение

```bash
git clone https://github.com/AVick23/test_project.git
cd test_project

python3.12 -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

### 2. Положить датасет MovieLens

Скачай **ml-latest-small** с
<https://grouplens.org/datasets/movielens/latest/> и распакуй в:

```
data/raw/ml-latest-small/
```

Внутри должны быть файлы:
```
movies.csv    ratings.csv    links.csv    tags.csv    README.txt
```

### 3. Залить данные в SQLite

```bash
python scripts/seed.py --reset
```

Ожидаемый результат:
```
==================================================
SEED COMPLETE
==================================================
  Movies:       9742  (with tmdb_id: 9733)
  Genres:       20
  Users:        610
  Interactions: 100836
  User states:  100836
==================================================
  Password for seeded users: 'demo123'
==================================================
```

Занимает **~30 секунд**. Пароль у всех готовых пользователей — `demo123`,
логины — `user_1`, `user_2`, …, `user_610`.

### 4. Запустить сервер

```bash
uvicorn backend.main:app --reload
```

Открыть в браузере:

| Что | Адрес |
|---|---|
| 🖥️ Фронтенд | <http://localhost:8000/app/> |
| 📖 Swagger UI (API) | <http://localhost:8000/docs> |
| ❤️ Health check | <http://localhost:8000/health> |

**Логин:** `user_1` / `demo123` (или любой из 610).

---

## 📝 Как работать с алгоритмами

### Контракт: три функции

Любой модуль в `algorithms/`, кроме `registry.py`, `dataset.py`, `topk.py`,
`metrics.py`, **должен содержать три функции**:

```python
def fit(dataset):
    """Обучить алгоритм на данных. Заполнить глобальное состояние."""
    ...

def similar_items(movie_id, k=10):
    """Top-k похожих фильмов на movie_id.
       Вернуть список кортежей: [(movie_id, score), ...]"""
    ...

def recommend_for_user(user_id, k=10):
    """Top-k рекомендаций для пользователя.
       Вернуть список кортежей: [(movie_id, score), ...]"""
    ...
```

Всё. Backend вызывает эти функции — больше ничего от алгоритма не требует.

### Регистрация алгоритма

Добавь свой модуль в `algorithms/registry.py`:

```python
MODULES = {
    "popularity": "algorithms.popularity",
    "jaccard":    "algorithms.content",
    "item_item":  "algorithms.item_item",
    "my_algo":    "algorithms.my_algo",     # ← твой
}
```

После этого:

```bash
curl http://localhost:8000/algorithms/list | python -m json.tool
```

Видish `"available": true` для своего алгоритма.

### Проверка работы

```bash
# Перестроить кэш для своего алгоритма (первые 200 фильмов)
python scripts/build_cache.py --algo=my_algo --limit=200

# Или сразу для всех
python scripts/build_cache.py --algo=all --limit=100
```

Открой <http://localhost:8000/app/> → «Алгоритмы» → выбери свой в списке.
Рекомендации на главной обновятся автоматически.

### Метрики

```bash
python -c "
from algorithms.dataset import load_dataset
from algorithms import metrics, popularity

ds = load_dataset()
popularity.fit(ds)
result = metrics.evaluate(popularity, ds, k=10)
print(result)
# {'precision': 0.12, 'recall': 0.05, 'ndcg': 0.10}
"
```

---

## 🔌 API — краткая шпаргалка

Все приватные роуты требуют заголовок `Authorization: Bearer <token>`.

### Auth
| Метод | Путь | Описание |
|---|---|---|
| POST | `/auth/register` | регистрация |
| POST | `/auth/login` | логин → JWT |
| GET  | `/auth/me` | текущий пользователь |

### Movies
| Метод | Путь | Описание |
|---|---|---|
| GET | `/movies?q=&genre=&year=&sort=&page=&limit=` | каталог с фильтрами |
| GET | `/movies/{id}` | один фильм |
| GET | `/movies/{id}/similar?algorithm=&k=` | похожие |

### Interactions
| Метод | Путь | Описание |
|---|---|---|
| POST | `/interactions` | записать действие |
| DELETE | `/interactions/{movie_id}?event_type=` | удалить действие |
| GET | `/users/me/state/{movie_id}` | состояние |
| GET | `/users/me/watched` | просмотренные |
| GET | `/users/me/watchlist` | хочу посмотреть |

### Recommendations
| Метод | Путь | Описание |
|---|---|---|
| GET | `/recommendations/me?algorithm=&k=` | рекомендации |

### Algorithms (dev)
| Метод | Путь | Описание |
|---|---|---|
| GET | `/algorithms/list` | доступные алгоритмы |
| GET | `/algorithms/compare?movie_id=&k=` | сравнить алгоритмы |
| POST | `/algorithms/rebuild?algorithm=` | перестроить кэш |

---

## 📚 Методические указания

В папке [`methodological_guides/`](methodological_guides/) лежат пошаговые
материалы курса:

| Файл | Что внутри |
|---|---|
| `01_intro.md` | Что такое рекомендательные системы. Три подхода. Как всё устроено |
| `02_registry.md` | Модули Python, реестр алгоритмов, первый PR |
| `03_dataset.md` | `numpy`, разреженные матрицы, инвертированный индекс |
| `04_popularity.md` | Baseline: popularity. Code Review, DoD |
| `05_content.md` | Jaccard, TF-IDF, косинус |
| `06_topk.md` | `sorted` vs `heapq.nlargest` vs `np.argpartition` |
| `07_metrics.md` | Precision@k, Recall@k, NDCG@k, train/test split |
| `08_item_item.md` | Collaborative filtering. Pair Programming |
| `09_mf.md` | Matrix factorization. SGD |

**Каждая методичка = один спринт** в терминах Agile. Внутри — мини-теория,
примеры на пальцах, задания и чек-листы.

Стартуй с `01_intro.md`.

---

## 🧭 Куда смотреть, если что-то не работает

| Симптом | Что делать |
|---|---|
| `ModuleNotFoundError: No module named 'passlib'` | Забыл активировать venv: `source .venv/bin/activate` |
| `movies: 0` в `/health` | Не запустил `python scripts/seed.py --reset` |
| `Data directory not found` в seed | Датасет не в `data/raw/ml-latest-small/` |
| `401 Unauthorized` при логине | Пароль не `demo123` или такого `user_N` нет |
| Пустой список рекомендаций | Не перестроил кэш: `python scripts/build_cache.py --algo=popularity` |
| `algorithms.registry` не видит модуль | Проверь `MODULES` и имя файла |
| `RuntimeError: my_algo missing fit` | Модуль не содержит одну из трёх функций |

---

## 🧹 Что НЕ нужно коммитить

Убедись, что в `.gitignore` есть:

```gitignore
__pycache__/
*.pyc
.venv/
venv/
data/movies.db*
data/dataset.pkl
data/raw/
.env
*.log
```

`data/raw/` не коммитится — датасет весит ~1 МБ, но его скачивают отдельно
с grouplens.org. `movies.db` — тоже локальный, создаётся через `seed.py`.

---

## 🗺️ Roadmap

- [x] Backend + frontend + БД
- [x] `seed.py` с датасетом MovieLens
- [x] `build_cache.py` с кэшем в БД
- [x] Реестр алгоритмов
- [ ] **`popularity.py`** ← базовая реализация (для студентов)
- [ ] **`content.py`** ← Jaccard + TF-IDF
- [ ] **`item_item.py`** ← collaborative filtering
- [ ] **`mf.py`** ← matrix factorization
- [ ] **`metrics.py`** ← Precision / Recall / NDCG
- [ ] **`topk.py`** ← сравнение top-K-методов

---

## 📜 Лицензия

Учебный проект. Использование в образовательных целях — свободное.
Датасет MovieLens — собственность GroupLens Research (Университет Миннесоты),
используется по их [условиям](https://grouplens.org/datasets/movielens/).

---

## 🙌 Благодарности

- **GroupLens Research** — за датасет MovieLens
- **FastAPI, SQLAlchemy, scipy, scikit-learn** — за инструменты
- **Студентам, которые писали алгоритмы** — за терпение и находчивость