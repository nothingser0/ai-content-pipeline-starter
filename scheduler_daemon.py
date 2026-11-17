#!/usr/bin/env python3
"""
Lightweight Scheduler Daemon for Docker
Sleeps quietly (<10MB RAM) and triggers `run_cron_daily` on scheduled time Monday-Friday.
Logs to stdout so output is visible in docker logs.
"""

import asyncio
import os
import signal
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from run import load_api_config, run_cron_daily

# Ensure .env is loaded first before reading environment variables
load_api_config()

TZ_NAME = os.getenv("TIMEZONE", "Asia/Jakarta")
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo(TZ_NAME)
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=7))

# Default trigger time: "03:00" (HH:MM WIB) - configurable via CRON_SCHEDULE in .env
SCHEDULE_TIME = os.getenv("CRON_SCHEDULE", "03:00").strip()
RUN_ON_STARTUP = os.getenv("RUN_ON_STARTUP", "false").strip().lower() in ("1", "true", "yes")
MAX_DAILY_ACCOUNTS = int(os.getenv("CRON_MAX_ACCOUNTS", "3"))


async def main() -> None:
    print("=" * 60)
    print("🚀 Content Pipeline Scheduler Daemon (Docker)")
    print(f"⏰ Timezone: {TZ_NAME}")
    print(f"📅 Daily Trigger Time: {SCHEDULE_TIME} (Mon-Fri)")
    print(f"🎯 Daily Target Posts: {MAX_DAILY_ACCOUNTS}")
    print(f"🔄 Run on Startup: {RUN_ON_STARTUP}")
    print("=" * 60)

    load_api_config()

    if RUN_ON_STARTUP:
        print("\n[STARTUP] RUN_ON_STARTUP is enabled. Running initial daily batch...")
        try:
            await run_cron_daily(max_accounts=MAX_DAILY_ACCOUNTS, force=True)
        except Exception as e:
            print(f"[ERROR] Startup execution failed: {e}")

    last_triggered_date = None

    while True:
        now = datetime.now(LOCAL_TZ)
        today_date_str = now.strftime("%Y-%m-%d")
        current_time_str = now.strftime("%H:%M")
        weekday = now.weekday()  # 0: Monday, 4: Friday, 5: Saturday, 6: Sunday

        # Trigger on scheduled time, only on Monday-Friday (0-4), once per day
        if (
            current_time_str == SCHEDULE_TIME
            and weekday < 5
            and last_triggered_date != today_date_str
        ):
            print(f"\n⏰ [{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] Triggering scheduled daily batch...")
            last_triggered_date = today_date_str
            try:
                await run_cron_daily(max_accounts=MAX_DAILY_ACCOUNTS)
            except Exception as e:
                print(f"[ERROR] Daily cron execution failed: {e}")

        # Sleep for 30 seconds before next check
        await asyncio.sleep(30)


if __name__ == "__main__":
    def _sig_handler(sig, frame):
        print("\n🛑 Signal received, shutting down gracefully...")
        sys.exit(0)

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _sig_handler)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _sig_handler)

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Scheduler daemon stopped.")
