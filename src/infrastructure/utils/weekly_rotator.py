"""
Weekly Account Rotator for Daily Cron Execution
Ensures daily target of posts (e.g. 21 posts/day) distributed across accounts,
capping each account at max 5 posts per week, auto-resetting every Monday.
"""

import json
import os
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Tuple

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Jakarta"))
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=7))

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
STATE_FILE = DATA_DIR / "weekly_state.json"
MAX_POSTS_PER_WEEK = int(os.getenv("WEEKLY_MAX_POSTS_PER_ACCOUNT", "5"))


def get_current_iso_week() -> str:
    """Return formatted ISO year and week string, e.g. '2026-W46'"""
    now = datetime.now(LOCAL_TZ)
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def load_state() -> dict[str, Any]:
    """Load weekly rotation state from file or initialize default."""
    current_week = get_current_iso_week()
    default_state = {
        "current_week": current_week,
        "account_counts": {},
        "completed_accounts": [],
        "total_posts_this_week": 0,
        "last_run_date": None,
    }

    if not STATE_FILE.exists():
        return default_state

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Auto-reset if a new calendar week has started
        if data.get("current_week") != current_week:
            return {
                "current_week": current_week,
                "account_counts": {},
                "completed_accounts": [],
                "total_posts_this_week": 0,
                "last_run_date": None,
            }

        # Backward compatibility
        if "account_counts" not in data:
            data["account_counts"] = {}
        if "total_posts_this_week" not in data:
            data["total_posts_this_week"] = sum(data.get("account_counts", {}).values())

        return data
    except Exception:
        return default_state


def save_state(state: dict[str, Any]) -> None:
    """Save weekly rotation state to JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def get_next_daily_accounts(
    all_accounts: list[str],
    max_count: int = 21,
    max_per_account: int = MAX_POSTS_PER_WEEK,
) -> Tuple[list[str], dict[str, Any]]:
    """
    Get up to max_count account slots for today whose weekly quota is not exhausted (< max_per_account).

    Returns:
        Tuple of (selected_accounts, current_state)
    """
    state = load_state()
    counts = state.get("account_counts", {})

    # Calculate remaining quota for each account
    remaining_quota: dict[str, int] = {}
    for acc in all_accounts:
        c = counts.get(acc, 0)
        if c < max_per_account:
            remaining_quota[acc] = max_per_account - c

    if not remaining_quota:
        return [], state

    # Build pool of slots to pick from
    # 1. First, pick unique available accounts (1 post per account for variety)
    available_unique = list(remaining_quota.keys())
    random.shuffle(available_unique)

    selected: list[str] = []
    
    # Take up to max_count unique accounts
    first_round = available_unique[:max_count]
    selected.extend(first_round)

    # 2. If we still need more slots to reach max_count (e.g. fewer than 21 unique accounts remaining),
    # fill from accounts that still have extra remaining quota
    if len(selected) < max_count:
        # Update remaining quota after first round
        for acc in first_round:
            remaining_quota[acc] -= 1

        extra_pool = []
        for acc, rem in remaining_quota.items():
            extra_pool.extend([acc] * rem)
        random.shuffle(extra_pool)

        needed = max_count - len(selected)
        selected.extend(extra_pool[:needed])

    # Shuffle the final selection order for daily execution variety
    random.shuffle(selected)
    return selected, state


def mark_account_done(
    account_id: str,
    state: dict[str, Any],
    max_per_account: int = MAX_POSTS_PER_WEEK,
) -> None:
    """Increment count for an account and mark completed if reached weekly cap."""
    if "account_counts" not in state:
        state["account_counts"] = {}
    if "completed_accounts" not in state:
        state["completed_accounts"] = []

    state["account_counts"][account_id] = state["account_counts"].get(account_id, 0) + 1
    state["total_posts_this_week"] = state.get("total_posts_this_week", 0) + 1

    if state["account_counts"][account_id] >= max_per_account:
        if account_id not in state["completed_accounts"]:
            state["completed_accounts"].append(account_id)

    now = datetime.now(LOCAL_TZ)
    state["last_run_date"] = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    save_state(state)
