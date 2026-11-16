"""
21 Accounts Content Pipeline - Main Runner
Simplified CLI wrapper - delegates to application modules
"""

import argparse
import asyncio
import json
import os
import random
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

# Initialize Sentry if enabled
try:
    import sentry_sdk

    SENTRY_DSN = os.getenv("SENTRY_DSN")
    if SENTRY_DSN:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
        )
except ImportError:
    pass

from src.application.angle_selector import AngleSelector
from src.application.orchestrator import PipelineOrchestrator
from src.application.services.package import create_final_package
from src.application.services.strategist import generate_angles
from src.application.topic_generator import select_rotating_pillar
from src.domain.repositories.account_repository import AccountRepository
from src.domain.services.deduplication import ContentDeduplicator
from src.domain.services.validation import ValidationError, validate_topic
from src.infrastructure.config.loader import load_api_config
from src.infrastructure.logging.logger import setup_logger
from src.infrastructure.monitoring.health import start_health_check_server
from src.infrastructure.utils.fresh_topics import fresh_topics_enabled, pick_fresh_topic
from src.integrations.discord_notifier import send_angle_notification, send_final_notification
from src.integrations.buffer_client import schedule_to_buffer
from src.infrastructure.utils.weekly_rotator import (
    get_next_daily_accounts,
    mark_account_done,
    load_state,
)
from src.infrastructure.storage.prune import prune_old_outputs

logger = setup_logger(__name__)

AccountConfig = dict[str, Any]
AngleData = dict[str, Any]

ACCOUNTS_PATH = PROJECT_ROOT / "accounts"
OUTPUT_PATH = PROJECT_ROOT / "output"
LOCAL_TZ = ZoneInfo("Asia/Jakarta") if ZoneInfo else timezone(timedelta(hours=7))
WEEKLY_ACCOUNT_GROUPS = {
    0: ["01-ai-automation", "02-indie-maker", "03-cybersecurity", "04-web-dev"],
    1: ["05-tech-news", "06-personal-finance", "07-stock-market", "08-freelance"],
    2: ["09-design", "10-meme", "11-productivity", "12-gaming"],
    3: ["13-fitness", "14-travel", "15-food-coffee", "16-local-news"],
    4: ["17-photography", "18-writing", "19-book-reviews", "20-music", "21-fikirlalu"]
}


def build_topic_from_history(
    account_config: AccountConfig,
    dedup: ContentDeduplicator,
    preferred_pillar: str | None = None,
) -> str:
    """Build topic from history with deduplication checks and fresh news priority."""
    selected_pillar = preferred_pillar or select_rotating_pillar(account_config, dedup)
    pillar_str = str(selected_pillar).lower()
    is_news_or_trend = any(k in pillar_str for k in ("news", "trend", "current", "event", "update"))

    # Try fresh topics first
    if fresh_topics_enabled():
        # Always try fresh topics for news/trends; 70% chance for other pillars
        fresh_chance = 1.0 if is_news_or_trend else 0.7
        import random

        if random.random() <= fresh_chance:
            fresh_topic = pick_fresh_topic(
                account_config,
                dedup.get_recent_topics(limit=20),
                preferred_pillar=selected_pillar,
            )
            if fresh_topic and not dedup.theme_seen_recently(fresh_topic, limit=20):
                return fresh_topic

    # Fallback to pillar-based topic
    niche = account_config.get("niche", "general")
    if selected_pillar:
        # If news pillar has no fresh live headline, avoid generic "news" that causes LLM to hallucinate stale news
        if is_news_or_trend:
            return f"{niche} - Practical industry insights and modern workflow analysis"
        return f"{niche} - {selected_pillar}"
    else:
        return niche


def load_account_config(account_id: str) -> AccountConfig:
    """Load account-specific configuration."""
    config_path = ACCOUNTS_PATH / account_id / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found for account: {account_id}")

    with open(config_path, "r", encoding="utf-8-sig") as file:
        return json.load(file)


def load_prompts(account_id: str) -> tuple[str, str]:
    """Load strategist and writer prompts for account."""
    account_dir = ACCOUNTS_PATH / account_id
    strategist_path = account_dir / "strategist_prompt.txt"
    writer_path = account_dir / "writer_prompt.txt"

    if not strategist_path.exists():
        raise FileNotFoundError(f"Strategist prompt not found for account: {account_id}")
    if not writer_path.exists():
        raise FileNotFoundError(f"Writer prompt not found for account: {account_id}")

    with open(strategist_path, "r", encoding="utf-8") as file:
        strategist_prompt = file.read()

    with open(writer_path, "r", encoding="utf-8") as file:
        writer_prompt = file.read()

    return strategist_prompt, writer_prompt


def create_content_folder(account_id: str, topic: str, content_format: str) -> Path:
    """Create timestamped content folder"""
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Remove invalid path characters
    safe_topic = topic[:30].replace(" ", "_").replace("/", "-").replace(":", "").replace("\\", "").replace("?", "").replace("*", "").replace('"', "").replace("<", "").replace(">", "").replace("|", "")
    safe_format = content_format.lower().replace(" ", "_")
    folder_name = f"{timestamp}_{safe_topic}_{safe_format}"

    folder_path = OUTPUT_PATH / account_id / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    return folder_path


def save_intermediate_files(
    content_folder: Path,
    angles: list[AngleData],
    selected_angle: AngleData,
    content: str,
    qc_result: dict[str, Any],
    visual_brief: str | None,
    engagement_strategy: str | None,
) -> None:
    """Save intermediate files to content folder"""
    # Save angles
    with open(content_folder / "angles.json", "w", encoding="utf-8") as f:
        json.dump(angles, f, indent=2, ensure_ascii=False)

    # Save selected angle
    with open(content_folder / "selected_angle.json", "w", encoding="utf-8") as f:
        json.dump(selected_angle, f, indent=2, ensure_ascii=False)

    # Save content
    with open(content_folder / "content.txt", "w", encoding="utf-8") as f:
        f.write(content)

    # Save QC result
    with open(content_folder / "qc_result.json", "w", encoding="utf-8") as f:
        json.dump(qc_result, f, indent=2, ensure_ascii=False)

    # Save visual brief if exists
    if visual_brief:
        with open(content_folder / "visual_brief.txt", "w", encoding="utf-8") as f:
            f.write(visual_brief)

    # Save engagement strategy if exists
    if engagement_strategy:
        with open(content_folder / "engagement_strategy.txt", "w", encoding="utf-8") as f:
            f.write(engagement_strategy)


def build_final_package_path(content_folder: Path) -> Path:
    """Build path for final package file"""
    return content_folder / "final.md"


def build_weekday_schedule(account_id: str, num_posts: int) -> list[datetime]:
    """Schedule posts across consecutive days, 1 post per day, starting tomorrow."""
    now = datetime.now(LOCAL_TZ)
    seed = f"{account_id}:{now.date().isoformat()}"
    rng = random.Random(seed)
    used: set[tuple[int, int]] = set()
    schedule: list[datetime] = []

    for day_offset in range(num_posts):
        # Schedule starting tomorrow (today + 1 + day_offset)
        scheduled_date = now.date() + timedelta(days=day_offset + 1)
        hour = rng.randint(8, 21)
        minute = rng.choice([0, 10, 15, 20, 30, 40, 45, 50])
        while (hour, minute) in used:
            hour = rng.randint(8, 21)
            minute = rng.choice([0, 10, 15, 20, 30, 40, 45, 50])
        used.add((hour, minute))
        scheduled_dt = datetime.combine(scheduled_date, time(hour=hour, minute=minute), tzinfo=LOCAL_TZ)
        schedule.append(scheduled_dt)

    return schedule


def build_format_schedule(account_id: str, num_posts: int = 5) -> list[str]:
    """
    Build format schedule respecting weekly limits from .env
    
    Args:
        account_id: Account identifier
        num_posts: Number of posts to schedule (default: 5)
        
    Returns:
        List of format strings respecting weekly limits
    
    Example:
        With limits Thread=1, Poll=2, Image=1, Single Tweet=0 (unlimited)
        Already generated: Thread=0, Poll=1, Image=0
        Returns: ['Thread', 'Poll', 'Image', 'Single Tweet', 'Single Tweet'] (shuffled)
    """
    from infrastructure.config.loader import load_weekly_limits
    
    dedup = ContentDeduplicator(account_id)
    limits = load_weekly_limits()
    
    formats = []
    
    # Map limit dict to format names
    format_limits = [
        ("Thread", limits.get("Thread", 0)),
        ("Poll", limits.get("Poll", 0)),
        ("Image", limits.get("Image", 0)),
    ]
    
    # Add limited formats based on remaining quota
    for format_name, limit in format_limits:
        if limit == 0:  # 0 = unlimited, skip for now
            continue
        
        # Get current count this week
        current_count = dedup._get_format_count_this_week(format_name)
        
        # Calculate remaining quota
        remaining = max(0, limit - current_count)
        
        # Add up to remaining quota (but not more than slots available)
        add_count = min(remaining, num_posts - len(formats))
        formats.extend([format_name] * add_count)
    
    # Fill remaining slots with Single Tweet (unlimited)
    while len(formats) < num_posts:
        formats.append("Single Tweet")
    
    # Shuffle order for variety (but keep quotas)
    random.shuffle(formats)
    
    return formats[:num_posts]


def get_available_daily_format(account_id: str, format_choice: str | None = None) -> str:
    """Determine best available format for account today respecting weekly limits."""
    if format_choice:
        return format_choice

    schedule = build_format_schedule(account_id, num_posts=5)
    if schedule:
        return schedule[0]
    return "Single Tweet"


async def run_pipeline(
    account_id: str,
    topic: str,
    format_choice: str | None = None,
    interactive: bool = False,
    randomize_format: bool = False,
    scheduled_at: datetime | None = None,
) -> Path:
    """
    Run full content generation pipeline for single account

    Args:
        account_id: Account identifier
        topic: Content topic
        format_choice: Optional format override
        interactive: If True, prompt for angle/format selection
        randomize_format: If True, randomly select format

    Returns:
        Path to final package file
    """
    # Load account config and prompts
    account_config = load_account_config(account_id)
    strategist_prompt, writer_prompt = load_prompts(account_id)

    # Determine format first based on weekly limits
    selected_format = get_available_daily_format(account_id, format_choice)

    # Generate single best angle
    print(f"\n[1/4] Generating angle for: {topic} (Target format: {selected_format})")
    angles_result = await generate_angles(
        topic=topic,
        strategist_prompt=strategist_prompt,
        account_config=account_config,
        target_format=selected_format,
    )

    if not angles_result or "angles" not in angles_result:
        raise RuntimeError("Failed to generate angles")

    angles: list[AngleData] = angles_result["angles"]

    if not angles:
        raise RuntimeError("No angles generated")

    # Select angle (single best angle)
    selector = AngleSelector(angles)
    selected_angle = selector.select(interactive=interactive)

    print(f"[4/4] Format: {selected_format}")

    # Run pipeline orchestrator
    orchestrator = PipelineOrchestrator(
        account_id=account_id,
        account_config=account_config,
        accounts_path=ACCOUNTS_PATH,
    )

    package_data = await orchestrator.run(
        topic=topic,
        angle=selected_angle,
        content_format=selected_format,
        writer_prompt=writer_prompt,
    )

    # Create content folder and save files
    content_folder = create_content_folder(account_id, topic, selected_format)
    print(f"\n📁 Content folder: {content_folder.name}")

    # Save intermediate files
    save_intermediate_files(
        content_folder,
        angles,
        selected_angle,
        package_data["content"],
        package_data["qc"],
        package_data.get("visual_brief"),
        package_data.get("engagement_strategy"),
    )
    
    # Send angle notification to Discord Channel A (non-blocking)
    try:
        angle_file = content_folder / "selected_angle.json"
        await asyncio.to_thread(
            send_angle_notification,
            account_id=account_id,
            topic=topic,
            angle_title=selected_angle.get("title", "Untitled"),
            angle_file=angle_file,
        )
    except Exception as e:
        print(f"⚠️  Discord angle notification failed: {e}")

    # Build and save final package
    package_output_file = build_final_package_path(content_folder)
    create_final_package(package_data, package_output_file)

    # Record deduplication
    dedup = ContentDeduplicator(account_id)
    dedup.record_generation(
        topic,
        selected_angle.get("title", "Untitled"),
        package_data["content"],
        selected_format,
        str(package_output_file),
    )

    print(f"\n✅ Content saved to: {content_folder / 'content.txt'}")
    print(f"✅ Final package saved to: {package_output_file}")

    # Post-generation integrations
    qc_score = package_data.get("qc", {}).get("overall_score", 0)
    
    # Discord notification (non-blocking)
    try:
        await asyncio.to_thread(
            send_final_notification,
            account_id=account_id,
            topic=topic,
            content_format=selected_format,
            qc_score=qc_score,
            final_file=package_output_file,
        )
    except Exception as e:
        print(f"⚠️  Discord notification failed: {e}")
    
    # Buffer scheduling (non-blocking)
    try:
        content_file = content_folder / "content.txt"
        await asyncio.to_thread(
            schedule_to_buffer,
            account_id=account_id,
            content_file=content_file,
            content_format=selected_format,
            scheduled_at=scheduled_at,
        )
    except Exception as e:
        print(f"⚠️  Buffer scheduling failed: {e}")

    return package_output_file


async def run_batch_pipeline(
    account_ids: list[str],
    topic: str,
    format_choice: str | None = None,
) -> list[Path]:
    """Run pipeline for multiple accounts with same topic"""
    results: list[Path] = []
    for account_id in account_ids:
        print(f"\n{'='*60}")
        print(f"Processing account: {account_id}")
        print(f"{'='*60}")
        result = await run_pipeline(
            account_id,
            topic,
            format_choice,
            interactive=False,
            randomize_format=False,
        )
        results.append(result)
    return results


async def run_batch_auto_pipeline(
    account_ids: list[str],
    format_choice: str | None = None,
    random_format: bool = False,
    pillar_overrides: dict[str, str] | None = None,
) -> list[Path]:
    """Run batch auto pipeline with optional per-account pillar overrides"""
    results: list[Path] = []
    overrides = pillar_overrides or {}

    for account_id in account_ids:
        account_key = account_id.strip()
        account_config = load_account_config(account_key)
        dedup = ContentDeduplicator(account_key)
        preferred_pillar = overrides.get(account_key)

        # Generate topic
        topic = build_topic_from_history(
            account_config, dedup, preferred_pillar=preferred_pillar
        )
        print(f"\nGenerated auto topic for {account_key}: {topic}")

        # Run pipeline
        final_format_choice = None if random_format else format_choice
        result = await run_pipeline(
            account_key,
            topic,
            final_format_choice,
            interactive=False,
            randomize_format=random_format,
        )
        results.append(result)

    return results


async def run_weekly_batch(account_ids: list[str] | None = None, dry_run: bool = False) -> list[Path]:
    """
    Generate five posts per account with retry and weekly limit enforcement.
    
    - Respects weekly limits from .env (WEEKLY_LIMIT_THREAD, etc.)
    - Retries failed generations up to 3 times
    - Ensures exactly 5 posts per account (or logs if unable)
    """
    today = datetime.now(LOCAL_TZ)
    selected_accounts = account_ids or WEEKLY_ACCOUNT_GROUPS.get(today.weekday(), [])
    if not selected_accounts:
        print("No weekly account group for today. Run on Monday-Friday or pass accounts.")
        return []

    results: list[Path] = []
    for account_id in selected_accounts:
        num_posts = 5  # Default for weekly batch
        format_schedule = build_format_schedule(account_id, num_posts)
        schedule = build_weekday_schedule(account_id, len(format_schedule))
        
        print(f"\nWeekly batch for {account_id}")
        print(f"Format schedule (respecting limits): {format_schedule}")
        
        successful_count = 0
        
        for index, (scheduled_at, format_type) in enumerate(zip(schedule, format_schedule), start=1):
            account_config = load_account_config(account_id)
            dedup = ContentDeduplicator(account_id)
            topic = build_topic_from_history(account_config, dedup)
            print(f"  {index}. {scheduled_at.strftime('%A %Y-%m-%d %H:%M %Z')} - {format_type} - {topic}")
            
            if dry_run:
                continue

            # Retry mechanism: up to 3 attempts per post
            max_retries = 3
            success = False
            
            for retry_attempt in range(max_retries):
                try:
                    result = await run_pipeline(
                        account_id,
                        topic,
                        format_choice=format_type,  # Use scheduled format
                        interactive=False,
                        randomize_format=False,      # No randomization
                        scheduled_at=scheduled_at,
                    )
                    results.append(result)
                    successful_count += 1
                    success = True
                    break  # Success, move to next post
                    
                except Exception as e:
                    logger.warning(f"Attempt {retry_attempt + 1}/{max_retries} failed for {format_type}: {e}")
                    if retry_attempt == max_retries - 1:
                        logger.error(f"Failed to generate {format_type} after {max_retries} attempts")
            
            if not success:
                print(f"    ❌ Failed to generate post {index} ({format_type}) after {max_retries} attempts")
        
        # Verify exactly 5 posts generated
        expected_count = len(schedule)
        if successful_count < expected_count:
            print(f"\n⚠️  Account {account_id}: Only {successful_count}/{expected_count} posts generated. Missing {expected_count - successful_count} post(s).")
        else:
            print(f"\n✅ Account {account_id}: All {successful_count}/{expected_count} posts generated successfully.")

    return results


async def run_cron_daily(
    max_accounts: int = 21,
    account_ids: list[str] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> list[Path]:
    """
    Run daily batch for up to `max_accounts` posts across accounts (Mon-Fri).
    Tracks posts per account for the week (max 5 per account) and auto-resets on Monday.
    """
    now = datetime.now(LOCAL_TZ)
    weekday = now.weekday()
    day_name = now.strftime("%A")

    if weekday in (5, 6) and not force:
        print(f"\n[CRON DAILY] Today is {day_name} (weekend). Pipeline only runs on weekdays (Monday-Friday).")
        print("Use --force to run on weekends.")
        return []

    repo = AccountRepository()
    all_accounts = account_ids or repo.list_accounts()

    selected_accounts, state = get_next_daily_accounts(all_accounts, max_count=max_accounts)
    current_week = state.get("current_week", "unknown")
    total_posts_so_far = state.get("total_posts_this_week", 0)
    completed_so_far = state.get("completed_accounts", [])
    max_week_posts = len(all_accounts) * 5

    print("\n" + "=" * 60)
    print(f"CRON DAILY BATCH - {day_name}, {now.strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"Week: {current_week} | Total accounts: {len(all_accounts)} (max 5 posts/account/week)")
    print(f"Week Progress: {total_posts_so_far}/{max_week_posts} posts | Accounts at max cap (5/5): {len(completed_so_far)}/{len(all_accounts)}")
    print(f"Selected for today ({len(selected_accounts)} posts): {selected_accounts}")
    print("=" * 60)

    if not selected_accounts:
        print(f"\nAll {len(all_accounts)} accounts have reached their weekly cap (5 posts each) for {current_week}.")
        print("Rotation will automatically reset on next Monday.")
        return []

    results: list[Path] = []
    for idx, account_id in enumerate(selected_accounts, start=1):
        print(f"\n[{idx}/{len(selected_accounts)}] Processing account: {account_id}")
        account_config = load_account_config(account_id)
        dedup = ContentDeduplicator(account_id)
        topic = build_topic_from_history(account_config, dedup)
        print(f"  Topic: {topic}")

        if dry_run:
            print(f"  [DRY-RUN] Skipped actual generation for {account_id}")
            continue

        success = False
        for attempt in range(1, 3):
            try:
                result = await run_pipeline(
                    account_id,
                    topic,
                    format_choice=None,
                    interactive=False,
                    randomize_format=True,
                    scheduled_at=None,
                )
                results.append(result)
                mark_account_done(account_id, state)
                print(f"  ✅ Completed {account_id}")
                success = True
                break
            except Exception as e:
                logger.warning(f"Attempt {attempt}/2 failed for {account_id}: {e}")
                if attempt < 2:
                    print(f"  ⚠️ Attempt {attempt} failed, retrying in 5s...")
                    await asyncio.sleep(5)
                else:
                    logger.error(f"Failed to process {account_id} after 2 attempts: {e}")
                    print(f"  ❌ Failed {account_id}: {e}")

        # Short cooldown between accounts to be gentle on CPU and API rate limits
        if success and idx < len(selected_accounts):
            await asyncio.sleep(2)

    # Summary
    updated_state = load_state()
    final_total_posts = updated_state.get("total_posts_this_week", 0)
    fully_completed_accounts = len(updated_state.get("completed_accounts", []))
    remaining_posts = max(0, max_week_posts - final_total_posts)
    print("\n" + "=" * 60)
    print(f"DAILY SUMMARY: {len(results)}/{len(selected_accounts)} posts generated successfully today.")
    print(f"Week Progress: {final_total_posts}/{max_week_posts} posts generated ({fully_completed_accounts}/{len(all_accounts)} accounts at max 5 posts, {remaining_posts} posts remaining this week).")
    print("=" * 60)

    # Auto-prune old outputs to prevent disk bloat
    try:
        prune_old_outputs(keep_days=7, max_keep_per_account=5, dry_run=dry_run)
    except Exception as e:
        logger.warning(f"Auto-pruning failed: {e}")

    return results


async def main() -> None:
    """CLI entrypoint"""
    load_api_config()
    default_cron_max = int(os.getenv("CRON_MAX_ACCOUNTS", "21"))

    parser = argparse.ArgumentParser(description="21 Accounts Content Pipeline")
    parser.add_argument("--list", action="store_true", help="List all accounts")
    parser.add_argument("--account", type=str, help="Account ID (e.g., 01-ai-automation)")
    parser.add_argument("--accounts", type=str, help="Comma-separated account IDs")
    parser.add_argument("--topic", type=str, help="Content topic")
    parser.add_argument("--format", dest="format_choice", type=str, help="Content format")
    parser.add_argument("--auto", action="store_true", help="Auto-generate topic")
    parser.add_argument(
        "--random-format",
        action="store_true",
        help="Use random format from suggested_formats",
    )
    parser.add_argument(
        "--pillar", type=str, help="Optional pillar override for auto topic generation"
    )
    parser.add_argument(
        "--weekly-batch",
        action="store_true",
        help="Generate 5 random-format auto posts for today's weekday account group and schedule next Mon-Fri",
    )
    parser.add_argument(
        "--weekly-batch-all",
        action="store_true",
        help="Generate weekly batch for all 21 accounts",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show weekly schedule plan without generating or posting",
    )
    parser.add_argument(
        "--schedule",
        type=str,
        help="Schedule posting time for single account (ISO format YYYY-MM-DD HH:MM, 'tomorrow', or 'next-monday')",
    )
    parser.add_argument(
        "--cron-daily",
        action="store_true",
        help="Run daily batch: pick up to 21 posts across accounts (Mon-Fri) with auto-reset next week",
    )
    parser.add_argument(
        "--cron-max",
        type=int,
        default=default_cron_max,
        help=f"Maximum accounts/posts to process in daily cron (default: {default_cron_max})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force run daily cron even on weekends",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Prune old output directories to save disk space",
    )
    parser.add_argument(
        "--keep-days",
        type=int,
        default=7,
        help="Days of output to keep during prune (default: 7)",
    )
    parser.add_argument(
        "--keep-max",
        type=int,
        default=5,
        help="Minimum newest outputs to protect per account during prune (default: 5)",
    )

    args = parser.parse_args()

    if args.prune:
        prune_old_outputs(
            keep_days=args.keep_days,
            max_keep_per_account=args.keep_max,
            dry_run=args.dry_run,
        )
        return

    load_api_config()
    if not args.cron_daily:
        start_health_check_server()

    if args.cron_daily:
        account_ids = None
        if args.accounts:
            account_ids = [
                account_id.strip()
                for account_id in args.accounts.split(",")
                if account_id.strip()
            ]
        await run_cron_daily(
            max_accounts=args.cron_max,
            account_ids=account_ids,
            dry_run=args.dry_run,
            force=args.force,
        )
        return

    # Parse schedule argument for single account commands
    scheduled_at = None
    if args.schedule:
        if args.schedule.lower() == "tomorrow":
            tomorrow = datetime.now(LOCAL_TZ) + timedelta(days=1)
            scheduled_at = datetime.combine(tomorrow.date(), time(10, 0), LOCAL_TZ)
        elif args.schedule.lower() == "next-monday":
            # Calculate next Monday
            now = datetime.now(LOCAL_TZ)
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0:  # Already Monday
                days_until_monday = 7
            next_monday = now.date() + timedelta(days=days_until_monday)
            scheduled_at = datetime.combine(next_monday, time(10, 0), LOCAL_TZ)
        else:
            # Try parsing as ISO format
            try:
                scheduled_at = datetime.fromisoformat(args.schedule)
                if scheduled_at.tzinfo is None:
                    scheduled_at = scheduled_at.replace(tzinfo=LOCAL_TZ)
            except ValueError:
                print(f"Error: Invalid schedule format '{args.schedule}'. Use ISO format (YYYY-MM-DD HH:MM), 'tomorrow', or 'next-monday'")
                return

    if args.weekly_batch or args.weekly_batch_all:
        # Determine which accounts to process
        if args.accounts:
            # Explicit accounts provided via --accounts
            account_ids = [
                account_id.strip()
                for account_id in args.accounts.split(",")
                if account_id.strip()
            ]
        elif args.weekly_batch_all:
            # All 21 accounts
            account_ids = [account for group in WEEKLY_ACCOUNT_GROUPS.values() for account in group]
        else:
            # Auto-detect based on today's weekday
            account_ids = None
        
        await run_weekly_batch(
            account_ids=account_ids,
            dry_run=args.dry_run,
        )
        return

    if args.list:
        repo = AccountRepository()
        account_ids = repo.list_accounts()
        print("\n" + "=" * 60)
        print("AVAILABLE ACCOUNTS")
        print("=" * 60)
        for account_id in account_ids:
            config = load_account_config(account_id)
            print(
                f"{account_id:25} {config.get('niche', 'unknown'):30} {config.get('username', 'unknown')}"
            )
        return

    if not args.account and not args.accounts:
        print("Error: --account or --accounts required")
        print("Use --list to see available accounts")
        return

    if not args.topic and not args.auto:
        print("Error: --topic required (or use --auto)")
        return

    try:
        if args.accounts:
            account_ids = [
                account_id.strip()
                for account_id in args.accounts.split(",")
                if account_id.strip()
            ]
            if not account_ids:
                raise ValueError("No valid account IDs in --accounts")

            # Redis enforcement removed - using JSON fallback for all scales
            # enforce_redis_for_scale(len(account_ids))

            if args.auto:
                overrides = (
                    {account_id: str(args.pillar) for account_id in account_ids}
                    if args.pillar
                    else None
                )
                await run_batch_auto_pipeline(
                    account_ids, args.format_choice, args.random_format, overrides
                )
            else:
                if not args.topic:
                    raise ValueError("--topic required when batch run does not use --auto")
                topic = validate_topic(args.topic)
                await run_batch_pipeline(account_ids, topic, args.format_choice)
        else:
            account_config = load_account_config(args.account)
            if args.auto:
                dedup = ContentDeduplicator(args.account)
                topic = build_topic_from_history(
                    account_config, dedup, preferred_pillar=args.pillar
                )
                print(f"Auto topic: {topic}")
            else:
                topic = validate_topic(str(args.topic))

            await run_pipeline(
                args.account,
                topic,
                args.format_choice,
                interactive=not args.auto,
                randomize_format=args.random_format,
                scheduled_at=scheduled_at,
            )
    except (FileNotFoundError, ValidationError, RuntimeError, ValueError) as error:
        print(f"Error: {error}")


if __name__ == "__main__":
    asyncio.run(main())
