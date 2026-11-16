"""
Discord notification integration for 21-accounts pipeline
Sends notifications to shared Discord channels for all accounts
"""

import json
import os
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _safe_filename(value: str, fallback: str = "content") -> str:
    """Create safe filename for Discord"""
    name = str(value or fallback)
    for old, new in [("/", "_"), ("\\", "_"), (" ", "_"), (":", "_")]:
        name = name.replace(old, new)
    return "".join(ch for ch in name if ch.isalnum() or ch in "._-")[:60] or fallback


def _send_discord_message(
    channel_id: str,
    content: str,
    file_path: Optional[Path] = None,
    filename: Optional[str] = None,
) -> bool:
    """Send message to Discord channel via bot"""
    token = os.getenv("DISCORD_TOKEN", "").strip()
    
    if not token or not channel_id:
        return False
    
    # Remove "Bot " prefix if present
    if token.lower().startswith("bot "):
        token = token[4:].strip()
    
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {token}"}
    
    try:
        if file_path and file_path.exists():
            # Send with file attachment
            payload = {"content": content}
            with open(file_path, "rb") as f:
                files = {
                    "payload_json": (None, json.dumps(payload), "application/json"),
                    "files[0]": (filename or file_path.name, f),
                }
                response = requests.post(url, headers=headers, files=files, timeout=20)
        else:
            # Send text only
            response = requests.post(
                url, headers=headers, json={"content": content}, timeout=20
            )
        
        if response.status_code in {200, 201}:
            return True
        
        logger.warning(
            f"Discord bot error {response.status_code}: {response.text[:300]}"
        )
        return False
    
    except Exception as e:
        logger.warning(f"Discord bot error: {e}")
        return False


def send_angle_notification(
    account_id: str,
    topic: str,
    angle_title: str,
    angle_file: Path,
) -> bool:
    """
    Send angle selection notification to Discord Channel A
    
    Args:
        account_id: Account identifier
        topic: Content topic
        angle_title: Selected angle title
        angle_file: Path to angle.json file
    
    Returns:
        True if sent successfully, False otherwise
    """
    channel_id = os.getenv("DISCORD_CHANNEL_A_ID", "").strip()
    
    if not channel_id:
        logger.debug("Discord Channel A not configured, skipping angle notification")
        return False
    
    message = (
        f"📝 **Angle Selected**\n"
        f"Account: `{account_id}`\n"
        f"Topic: {topic}\n"
        f"Angle: {angle_title}"
    )
    
    filename = _safe_filename(f"{account_id}_angle.json")
    
    success = _send_discord_message(
        channel_id=channel_id,
        content=message,
        file_path=angle_file,
        filename=filename,
    )
    
    if success:
        logger.info(f"Discord: Angle notification sent for {account_id}")
    else:
        logger.warning(f"Discord: Failed to send angle notification for {account_id}")
    
    return success


def send_final_notification(
    account_id: str,
    topic: str,
    content_format: str,
    qc_score: int,
    final_file: Path,
) -> bool:
    """
    Send final package notification to Discord Channel B
    
    Args:
        account_id: Account identifier
        topic: Content topic
        content_format: Content format (Thread, Single Tweet, Poll, Image)
        qc_score: QC score (0-10)
        final_file: Path to final.md file
    
    Returns:
        True if sent successfully, False otherwise
    """
    channel_id = os.getenv("DISCORD_CHANNEL_B_ID", "").strip()
    
    if not channel_id:
        logger.debug("Discord Channel B not configured, skipping final notification")
        return False
    
    message = (
        f"✅ **Content Generated**\n"
        f"Account: `{account_id}`\n"
        f"Format: {content_format}\n"
        f"Topic: {topic}\n"
        f"QC Score: {qc_score}/10"
    )
    
    filename = _safe_filename(f"{account_id}_{content_format}_final.md")
    
    success = _send_discord_message(
        channel_id=channel_id,
        content=message,
        file_path=final_file,
        filename=filename,
    )
    
    if success:
        logger.info(f"Discord: Final notification sent for {account_id}")
    else:
        logger.warning(f"Discord: Failed to send final notification for {account_id}")
    
    return success
