"""
Buffer API integration for 21-accounts pipeline
Handles per-account Buffer scheduling with individual credentials using GraphQL API
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _is_buffer_enabled() -> bool:
    """Check if Buffer integration is globally enabled"""
    val = os.getenv("BUFFER_ENABLED", "true").strip().lower()
    return val not in {"0", "false", "no", "off"}


def _load_account_buffer_config(account_id: str) -> Optional[dict]:
    """
    Load Buffer credentials for specific account
    
    Args:
        account_id: Account identifier
    
    Returns:
        Dict with 'access_token' and 'channel_id', or None if not configured
    """
    config_file = PROJECT_ROOT / "accounts" / account_id / "buffer.json"
    
    if not config_file.exists():
        logger.debug(f"Buffer config not found for {account_id}: {config_file}")
        return None
    
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        token = config.get("buffer_access_token", "").strip()
        channel_id = config.get("buffer_profile_id", "").strip()
        
        if not token or not channel_id:
            logger.warning(
                f"Buffer config incomplete for {account_id}: missing token or profile_id"
            )
            return None
        
        return {
            "access_token": token,
            "channel_id": channel_id,
        }
    
    except Exception as e:
        logger.warning(f"Failed to load Buffer config for {account_id}: {e}")
        return None


def _clean_text_block(text: str) -> str:
    """Clean text block by removing empty lines at start/end"""
    lines = [line.strip() for line in text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines).strip()


def _strip_trailing_noise(text: str) -> str:
    """Remove trailing markers and noise from content"""
    # Split at common section markers
    text = re.split(r"\n-{3,}\n|\n\*\*[^\n]+:\*\*\s*$", text, maxsplit=1)[0]
    return _clean_text_block(text)


def _parse_content_for_buffer(content_file: Path, content_format: str) -> dict:
    """
    Parse content.txt file for Buffer API payload
    
    Args:
        content_file: Path to content.txt
        content_format: Content format (Thread, Single Tweet, Poll, Image)
    
    Returns:
        Dict with 'text' or 'thread' key for Buffer API
    
    Raises:
        ValueError: If content cannot be parsed
    """
    if not content_file.exists():
        raise ValueError(f"Content file not found: {content_file}")
    
    text = content_file.read_text(encoding="utf-8")
    format_lower = content_format.lower()
    
    # Single Tweet
    if "single tweet" in format_lower or format_lower == "tweet":
        match = re.search(r"\*\*SINGLE TWEET:\*\*\s*(.*)", text, re.S | re.I)
        if not match:
            raise ValueError("Cannot parse Single Tweet content")
        
        body = _strip_trailing_noise(match.group(1))
        if not body:
            raise ValueError("Empty Single Tweet content")
        
        return {"text": body}
    
    # Thread
    if "thread" in format_lower:
        tweets = [
            _clean_text_block(m.group(1))
            for m in re.finditer(
                r"\*\*Tweet \d+:\*\*\s*(.*?)(?=\n\*\*Tweet \d+:\*\*|\Z)",
                text,
                re.S | re.I,
            )
        ]
        tweets = [tweet for tweet in tweets if tweet]
        
        if not tweets:
            raise ValueError("Cannot parse Thread content")
        
        return {"thread": tweets}
    
    # Poll
    if "poll" in format_lower:
        match = re.search(r"\*\*POLL:\*\*\s*\n\s*\n(.+?)(?=\n\n|\Z)", text, re.S | re.I)
        if not match:
            raise ValueError("Cannot parse Poll content")
        
        body = _clean_text_block(match.group(1))
        if not body:
            raise ValueError("Empty Poll content")
        
        return {"text": body}
    
    # Image
    if "image" in format_lower:
        # Try new format: CAPTION: text
        match = re.search(r"\*\*IMAGE:\*\*\s*\n\s*CAPTION:\s*(.+?)(?=\n\n|\Z)", text, re.S | re.I)
        if not match:
            # Try old format: **Caption:**
            match = re.search(r"\*\*IMAGE:\*\*\s*\n\s*\n\s*\*\*Caption:\*\*\s*\n(.+?)(?=\n\n|\Z)", text, re.S | re.I)
        
        if not match:
            raise ValueError("Cannot parse Image content")
        
        body = _clean_text_block(match.group(1))
        if not body:
            raise ValueError("Empty Image content")
        
        return {"text": body}
    
    raise ValueError(f"Unsupported content format: {content_format}")


def _to_buffer_due_at(scheduled_at: datetime | None) -> str | None:
    if scheduled_at is None:
        return None

    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)

    return scheduled_at.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _create_graphql_mutation(
    text: str,
    channel_id: str,
    thread_tweets: Optional[list] = None,
    scheduled_at: datetime | None = None,
) -> dict:
    """
    Build Buffer GraphQL mutation for a single post or thread
    
    Args:
        text: Post text content (for single posts, or first tweet for threads)
        channel_id: Buffer channel ID
        thread_tweets: List of tweet texts for thread format (optional)
    
    Returns:
        Dict with query and variables for GraphQL request
    """
    due_at = _to_buffer_due_at(scheduled_at)
    mode = "customScheduled" if due_at else "addToQueue"
    due_at_line = f',\n            dueAt: "{due_at}"' if due_at else ""

    # Thread format with Twitter metadata
    if thread_tweets:
        # Build thread array with text and empty assets for each tweet
        thread_items = [
            {"text": tweet, "assets": []}
            for tweet in thread_tweets
        ]
        
        # First tweet text for main text field
        first_tweet = thread_tweets[0]
        
        query = f"""
        mutation CreatePost($text: String!, $thread: [ThreadedPostInput!]!) {{
          createPost(input: {{
            text: $text,
            channelId: "{channel_id}",
            schedulingType: automatic,
            mode: {mode}{due_at_line},
            assets: [],
            metadata: {{
              twitter: {{
                thread: $thread
              }}
            }}
          }}) {{
            ... on PostActionSuccess {{
              post {{
                id
                text
                dueAt
              }}
            }}
            ... on MutationError {{
              message
            }}
          }}
        }}
        """
        
        return {
            "query": query,
            "variables": {
                "text": first_tweet,
                "thread": thread_items
            }
        }
    
    # Single post format
    else:
        query = f"""
        mutation CreatePost($text: String!) {{
          createPost(input: {{
            text: $text,
            channelId: "{channel_id}",
            schedulingType: automatic,
            mode: {mode}{due_at_line},
            assets: []
          }}) {{
            ... on PostActionSuccess {{
              post {{
                id
                text
                dueAt
              }}
            }}
            ... on MutationError {{
              message
            }}
          }}
        }}
        """
        
        return {
            "query": query,
            "variables": {
                "text": text
            }
        }


def schedule_to_buffer(
    account_id: str,
    content_file: Path,
    content_format: str,
    scheduled_at: datetime | None = None,
) -> bool:
    """
    Schedule content to Buffer for specific account using GraphQL API
    
    Args:
        account_id: Account identifier
        content_file: Path to content.txt file
        content_format: Content format (Thread, Single Tweet, Poll, Image)
    
    Returns:
        True if scheduled successfully or skipped, False on error
    """
    # Check if Buffer globally enabled
    if not _is_buffer_enabled():
        logger.debug("Buffer integration disabled globally, skipping")
        return True
    
    # Load account-specific Buffer config
    config = _load_account_buffer_config(account_id)
    if not config:
        logger.debug(f"Buffer: No credentials for {account_id}, skipping")
        return True
    
    try:
        # Parse content
        parsed = _parse_content_for_buffer(content_file, content_format)
        
        # Handle thread format with Twitter metadata
        if "thread" in parsed:
            thread_tweets = parsed["thread"]
            graphql_payload = _create_graphql_mutation(
                text=thread_tweets[0],
                channel_id=config["channel_id"],
                thread_tweets=thread_tweets,
                scheduled_at=scheduled_at,
            )
            
            response = requests.post(
                "https://api.buffer.com",
                headers={
                    "Authorization": f"Bearer {config['access_token']}",
                    "Content-Type": "application/json",
                },
                json=graphql_payload,
                timeout=30,
            )
            
            if response.status_code in {200, 201}:
                result = response.json()
                
                # Check for errors
                if "errors" in result:
                    error_msg = result["errors"][0].get("message", "Unknown error")
                    logger.error(f"Buffer GraphQL error for {account_id}: {error_msg}")
                    return False
                
                if "data" in result and "createPost" in result["data"]:
                    create_post = result["data"]["createPost"]
                    if "message" in create_post:
                        logger.error(f"Buffer API error for {account_id}: {create_post['message']}")
                        return False
                    
                    suffix = f" at {scheduled_at.isoformat()}" if scheduled_at else ""
                    logger.info(f"Buffer: Scheduled thread with {len(thread_tweets)} tweets for {account_id}{suffix}")
                    return True
            
            logger.error(
                f"Buffer API error for {account_id}: {response.status_code} - {response.text[:200]}"
            )
            return False
        
        # Handle single post formats (Single Tweet, Poll, Image)
        else:
            text = parsed.get("text", "")
            graphql_payload = _create_graphql_mutation(
                text,
                config["channel_id"],
                scheduled_at=scheduled_at,
            )
            
            response = requests.post(
                "https://api.buffer.com",
                headers={
                    "Authorization": f"Bearer {config['access_token']}",
                    "Content-Type": "application/json",
                },
                json=graphql_payload,
                timeout=30,
            )
            
            if response.status_code in {200, 201}:
                result = response.json()
                
                # Check for GraphQL errors
                if "errors" in result:
                    error_msg = result["errors"][0].get("message", "Unknown error")
                    logger.error(f"Buffer GraphQL error for {account_id}: {error_msg}")
                    return False
                
                # Check for mutation error
                if "data" in result and "createPost" in result["data"]:
                    create_post = result["data"]["createPost"]
                    if "message" in create_post:
                        logger.error(f"Buffer API error for {account_id}: {create_post['message']}")
                        return False
                    
                    suffix = f" at {scheduled_at.isoformat()}" if scheduled_at else ""
                    logger.info(f"Buffer: Scheduled content for {account_id} ({content_format}){suffix}")
                    return True
            
            logger.error(
                f"Buffer API error for {account_id}: {response.status_code} - {response.text[:200]}"
            )
            return False
    
    except ValueError as e:
        logger.error(f"Buffer: Content parse error for {account_id}: {e}")
        return False
    
    except requests.RequestException as e:
        logger.error(f"Buffer: API request failed for {account_id}: {e}")
        return False
    
    except Exception as e:
        logger.error(f"Buffer: Unexpected error for {account_id}: {e}")
        return False
