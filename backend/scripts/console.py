"""Console helpers shared by the scripts."""

import sys

from app.config import settings


def setup_output() -> None:
    """Make stdout and stderr UTF-8 so Cyrillic survives pipes and redirects."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")


def database_label() -> str:
    """Describe the database the scripts are about to touch."""
    return (
        f"{settings.postgres_db} "
        f"({settings.postgres_host}:{settings.postgres_port})"
    )


def confirm_wipe(assume_yes: bool) -> bool:
    """Ask before deleting every row of the database.

    Args:
        assume_yes: Skip the question (the `--yes` flag).

    Returns:
        True when the wipe may go ahead.
    """
    warning = f"ALL DATA in database {database_label()} will be deleted."
    if assume_yes:
        print(warning)
        return True
    answer = input(f"{warning} Continue? [y/N] ")
    return answer.strip().lower() in ("y", "yes")
