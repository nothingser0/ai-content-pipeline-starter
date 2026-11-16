"""
Output Directory Pruning / Cleanup Utility
Deletes old generated content folders to save disk space,
while safely preserving deduplication history files (.content_history.json).
"""

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Asia/Jakarta")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=7))

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = PROJECT_ROOT / "output"


def prune_old_outputs(
    keep_days: int = 7,
    max_keep_per_account: int = 5,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Prune old output directories across all accounts.
    
    Rules:
    - Retains .content_history.json and hidden files (.versions, etc.)
    - Removes folders older than `keep_days`, keeping at least the latest `max_keep_per_account` folders.
    - If `keep_days == 0`, strictly keeps only `max_keep_per_account` newest folders.

    Returns:
        Dict with count of deleted folders and freed space in MB.
    """
    if not OUTPUT_DIR.exists():
        return {"deleted_count": 0, "freed_mb": 0}

    deleted_count = 0
    freed_bytes = 0
    now = datetime.now(LOCAL_TZ)
    cutoff_date = now - timedelta(days=keep_days) if keep_days > 0 else None

    print(f"\n🧹 Running Output Pruning (keep_days={keep_days}, max_keep_per_account={max_keep_per_account})...")

    for account_dir in OUTPUT_DIR.iterdir():
        if not account_dir.is_dir() or account_dir.name.startswith("."):
            continue

        # Collect all generated timestamped subdirectories
        subdirs = []
        for item in account_dir.iterdir():
            # Never prune hidden files/dirs like .content_history.json or .versions
            if item.name.startswith("."):
                continue
            if item.is_dir():
                subdirs.append(item)

        # Sort newest first based on folder name / modification time
        subdirs.sort(key=lambda p: p.name, reverse=True)

        # Folders to keep: the newest N folders are protected
        protected_subdirs = set(subdirs[:max_keep_per_account])

        for folder in subdirs:
            if folder in protected_subdirs and cutoff_date is not None:
                continue

            should_delete = False

            if cutoff_date is not None:
                # Check modification time
                folder_mtime = datetime.fromtimestamp(folder.stat().st_mtime, tz=LOCAL_TZ)
                if folder_mtime < cutoff_date and folder not in protected_subdirs:
                    should_delete = True
            else:
                # When keep_days == 0, delete everything beyond max_keep_per_account
                if folder not in protected_subdirs:
                    should_delete = True

            if should_delete:
                folder_size = sum(f.stat().st_size for f in folder.glob("**/*") if f.is_file())
                freed_bytes += folder_size
                deleted_count += 1

                if dry_run:
                    print(f"  [DRY-RUN] Would delete: {folder.relative_to(PROJECT_ROOT)}")
                else:
                    try:
                        shutil.rmtree(folder)
                        logger.debug(f"Deleted old output: {folder.name}")
                    except Exception as e:
                        logger.warning(f"Failed to delete {folder}: {e}")

    freed_mb = round(freed_bytes / (1024 * 1024), 2)
    action = "Would delete" if dry_run else "Deleted"
    print(f"✨ Pruning complete: {action} {deleted_count} old folders, freed ~{freed_mb} MB.")
    return {"deleted_count": deleted_count, "freed_mb": freed_mb}
