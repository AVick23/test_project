"""
Movie-Rec backend package.

Подпакеты и модули:
    db          — SQLAlchemy engine, SessionLocal, get_db dependency
    models      — ORM-модели (Movie, Genre, User, Interaction, ...)
    schemas     — Pydantic-схемы для API
    auth        — bcrypt + JWT, FastAPI dependencies
    services    — бизнес-логика (взаимодействия, рекомендации, кэши)
    main        — FastAPI app + все роуты
"""