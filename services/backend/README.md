# Backend

FastAPI service for the board game rental. This stage covers the database
layer: SQLAlchemy models, Alembic migrations, CRUD and the service layer.

Commands run from this directory. Python 3.14 and [uv](https://docs.astral.sh/uv/)
are required; the settings are read from `../.env` (see `../.env.example`).

## Setup

```
uv sync
uv run alembic upgrade head
```

## Seed and demo

```
uv run python -m scripts.seed --reset     # wipe the database and fill it
uv run python -m scripts.demo             # play the four scenarios of the report
```

`seed` without `--reset` refuses to touch a database that already has data.
Both scripts ask before wiping; pass `--yes` to skip the question. Every seeded
account uses the password defined in `scripts/seed.py`.

## Tests

```
uv run pytest
```

**The tests delete all rows of every table.** Run them on a database you can
lose, or point them at a separate one:

```
POSTGRES_DB=boardgame_test uv run pytest
```

(PowerShell: `$env:POSTGRES_DB = "boardgame_test"` first. The database must
exist and be migrated.)

## Layout

| Path | Role |
|---|---|
| `app/db/models/` | SQLAlchemy models |
| `app/schemas/` | Pydantic contracts |
| `app/crud/` | Queries, one class per table |
| `app/services/` | Business rules and transactions |
| `alembic/` | Migrations |
| `scripts/` | Seed and demo |
| `tests/` | Tests |
