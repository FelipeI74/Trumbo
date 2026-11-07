from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path
import shutil

from app import database


BACKUP_LIMIT = 5


def _directory_size(path: Path) -> int:
    total_size = 0
    for root, _, filenames in os.walk(path):
        total_size += sum(
            os.path.getsize(Path(root) / filename)
            for filename in filenames
        )
    return total_size


def _rotate_backups(backup_directory: Path) -> None:
    database_backups = sorted(backup_directory.glob("trumbo_*.db"))
    for old_backup in database_backups[:-BACKUP_LIMIT]:
        old_backup.unlink()

    data_backups = sorted(
        path
        for path in backup_directory.glob("data_*")
        if path.is_dir()
    )
    for old_backup in data_backups[:-BACKUP_LIMIT]:
        shutil.rmtree(old_backup)


def _next_backup_time(backup_directory: Path) -> datetime:
    timestamp_format = "%Y-%m-%d_%H%M%S"
    latest_backup_time = None

    backup_paths = [
        *backup_directory.glob("trumbo_*.db"),
        *backup_directory.glob("data_*"),
    ]
    for path in backup_paths:
        timestamp = (
            path.stem.removeprefix("trumbo_")
            if path.suffix == ".db"
            else path.name.removeprefix("data_")
        )
        try:
            backup_time = datetime.strptime(timestamp, timestamp_format)
        except ValueError:
            continue
        if latest_backup_time is None or backup_time > latest_backup_time:
            latest_backup_time = backup_time

    backup_time = datetime.now()
    if latest_backup_time is not None and latest_backup_time.strftime(
        timestamp_format
    ) >= backup_time.strftime(timestamp_format):
        backup_time = latest_backup_time + timedelta(seconds=1)
    return backup_time


def create_backup() -> dict[str, str | int]:
    database_path = Path(database.DB_PATH)
    backup_directory = database_path.parent / "ADUMN_BACKUPS"
    backup_time = _next_backup_time(backup_directory)
    timestamp = backup_time.strftime("%Y-%m-%d_%H%M%S")
    projects_directory = database_path.parent / "data" / "projects"
    backup_directory.mkdir(parents=True, exist_ok=True)

    database_backup = backup_directory / f"trumbo_{timestamp}.db"
    shutil.copy2(database_path, database_backup)

    data_backup = None
    if projects_directory.is_dir():
        data_backup = backup_directory / f"data_{timestamp}"
        shutil.copytree(projects_directory, data_backup)

    _rotate_backups(backup_directory)

    size_bytes = database_backup.stat().st_size
    if data_backup is not None:
        size_bytes += _directory_size(data_backup)

    return {
        "path": str(database_backup),
        "size_bytes": size_bytes,
        "timestamp": timestamp,
    }
