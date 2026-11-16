"""
Create new account with AI-generated strategist and writer prompts
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"

# Add both project root and src to path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import requests

from infrastructure.config.loader import load_api_config


def generate_strategist_prompt(account_data: dict) -> str:
    """Generate strategist prompt using AI
    
    Args:
        account_data: Account configuration with niche, positioning, target_audience, voice
        
    Returns:
        Generated strategist prompt text
    """
    api_url, api_key, model = load_api_config()

    system_prompt = """You are an expert content strategist. Generate a strategist prompt for a content creator account.

The prompt should:
1. Define the account positioning and target audience
2. List content pillars with priority percentages (must sum to 100%)
3. Define language style and voice
4. List available formats (Single Tweet, Thread, Poll, Image)
5. Include output format as JSON with angles structure
6. Include scoring guide and examples

Use this template structure but customize for the niche:

# AI STRATEGIST - [NICHE]

## INPUT
{topics}

## TASK
Generate 10 content angles for the topic above.

## POSITIONING
Account: "[positioning]"
Target: [target_audience]
Voice: [voice]

## CONTENT FOCUS (Priority Order)
[List 4 content pillars with percentages]

## LANGUAGE STYLE
[3-4 bullet points describing style]

## AVAILABLE FORMATS
1. **Single Tweet** - Quick tip, hot take (max 280 char, can end naturally without forced questions)
2. **Thread** - Tutorial, story, deep dive (4-8 tweets, AI decides based on content depth)
3. **Poll** - Engagement, survey, opinion (4 options)
4. **Image** - Visual post with caption

## OUTPUT FORMAT (JSON)
[Include full JSON structure with angles array]

## SCORING GUIDE
- **value_score** (1-10): How actionable/useful
- **effort_estimate**: Realistic implementation time
- **viral_score** (1-10): Viral potential
- **recency_score** (1-10): How trending/timely

## EXAMPLES
[3 good angles, 3 bad angles specific to niche]

Generate 10 angles now!"""

    user_prompt = f"""Generate strategist prompt for:

Niche: {account_data['niche']}
Positioning: {account_data['positioning']}
Target Audience: {account_data['target_audience']}
Voice: {account_data['voice']}

Content Pillars (suggest 4 relevant pillars with percentages that sum to 100%):
- Based on the niche, suggest appropriate content categories

Return ONLY the strategist prompt text, no markdown code blocks."""

    response = requests.post(
        f"{api_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
        },
    )

    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def generate_writer_prompt(account_data: dict) -> str:
    """Generate writer prompt using AI
    
    Args:
        account_data: Account configuration with niche, positioning, voice
        
    Returns:
        Generated writer prompt text
    """
    api_url, api_key, model = load_api_config()

    system_prompt = """You are an expert content writer. Generate a writer prompt for a content creator account.

The prompt should:
1. Include angle variables (title, hook, key_points, cta, pillar)
2. Define format variable
3. List content structure for each format (Thread, Single Tweet, Poll, Image)
4. Include language style and voice
5. Provide format-specific examples
6. Include quality checklist

Use this template structure but customize for the niche:

# AI WRITER - [NICHE]

## ANGLE SELECTED
**Title:** {title}
**Hook:** {hook}
**Key Points:** {key_points}
**CTA:** {cta}
**Pillar:** {pillar}

## FORMAT
{format}

## TASK
Generate full content based on the ANGLE above for format {format}.

IMPORTANT:
1. Content MUST match the title and key points from angle
2. ONLY generate format {format} requested
3. Follow EXACT structure for format {format}

## LANGUAGE STYLE
[3-4 bullet points describing voice and style]

## CONTENT STRUCTURE

**Thread (4-8 tweets, AI decides based on content depth):**
CRITICAL: Each tweet MUST be 200-250 chars. This is NON-NEGOTIABLE.
- Tweet 1 = hook (200-250 chars) - strong, specific opening
- Tweets 2-7 = body (200-250 chars EACH) - detailed, with examples/data
- Last tweet = CTA or question (180-220 chars)
[Define narrative flow and structure]

**Single Tweet (<280 chars, target 200-240 chars):**
- Structure: observation + implication (can end naturally)
- Can end with statement, insight, or question - not forced
- Natural sentence flow, not compressed list
- Reads like something posted at 11pm, not scheduled at 9am
[Define structure and voice]

**Poll:**
[Define structure]

**Image:**
[Define structure]

## EXAMPLES
[2-3 examples specific to niche and voice]

## QUALITY CHECKLIST
- [ ] Hook is engaging (not generic)
- [ ] Language is natural and clear
- [ ] Examples are concrete (not just theory)
- [ ] Actionable (audience can try immediately)
- [ ] CTA is specific (not "drop a number")
- [ ] Format is correct (as requested)

Generate content now!"""

    user_prompt = f"""Generate writer prompt for:

Niche: {account_data['niche']}
Voice: {account_data['voice']}
Target Audience: {account_data['target_audience']}

Return ONLY the writer prompt text, no markdown code blocks."""

    response = requests.post(
        f"{api_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
        },
    )

    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def create_account(
    account_id: str,
    username: str,
    name: str,
    niche: str,
    positioning: str,
    target_audience: str,
    voice: str,
):
    """Create new account with AI-generated prompts"""

    accounts_path = PROJECT_ROOT / "accounts"
    account_path = accounts_path / account_id

    # Check if exists
    if account_path.exists():
        print(f"Error: Account {account_id} already exists")
        return False

    # Create folder
    account_path.mkdir(parents=True, exist_ok=True)
    print(f"Created folder: {account_path}")

    # Prepare account data
    account_data = {
        "account_id": account_id,
        "username": username,
        "name": name,
        "niche": niche,
        "positioning": positioning,
        "target_audience": target_audience,
        "voice": voice,
    }

    # Generate prompts with AI
    print("\nGenerating strategist prompt with AI...")
    strategist_prompt = generate_strategist_prompt(account_data)

    print("Generating writer prompt with AI...")
    writer_prompt = generate_writer_prompt(account_data)

    # Create config.json (with placeholder pillars)
    config = {
        "account_id": account_id,
        "username": username,
        "name": name,
        "niche": niche,
        "positioning": positioning,
        "target_audience": target_audience,
        "voice": voice,
        "content_pillars": {"pillar1": 40, "pillar2": 30, "pillar3": 20, "pillar4": 10},
        "preferred_formats": ["Thread", "Single Tweet", "Poll", "Image"],
        "posting_frequency": {"daily": 1, "weekly_threads": 2, "monthly_deep_dives": 1},
        "airdrop_compatibility": "medium",
        "crypto_angle": "none",
    }

    config_path = account_path / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    print(f"Created: {config_path}")

    # Save strategist prompt
    strategist_path = account_path / "strategist_prompt.txt"
    with open(strategist_path, "w", encoding="utf-8") as f:
        f.write(strategist_prompt)
    print(f"Created: {strategist_path}")

    # Save writer prompt
    writer_path = account_path / "writer_prompt.txt"
    with open(writer_path, "w", encoding="utf-8") as f:
        f.write(writer_prompt)
    print(f"Created: {writer_path}")

    # Create buffer.json template
    buffer_template = {
        "buffer_access_token": "YOUR_BUFFER_ACCESS_TOKEN_HERE",
        "buffer_profile_id": "YOUR_BUFFER_CHANNEL_ID_HERE"
    }
    buffer_path = account_path / "buffer.json.template"
    with open(buffer_path, "w", encoding="utf-8") as f:
        json.dump(buffer_template, f, indent=4, ensure_ascii=False)
    print(f"Created: {buffer_path}")

    print(f"\n[OK] Account {account_id} created successfully!")
    print(f"\nNext steps:")
    print(f"1. Edit {config_path} to update content_pillars")
    print(f"2. Review and customize {strategist_path}")
    print(f"3. Review and customize {writer_path}")
    print(f"4. (Optional) Setup Buffer: rename {buffer_path} to buffer.json and add credentials")
    print(f"5. Run: python run.py --account {account_id} --auto")

    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Create new account with AI-generated prompts"
    )
    parser.add_argument(
        "--account-id", required=True, help="Account ID (e.g., 22-new-niche)"
    )
    parser.add_argument("--username", required=True, help="Username (e.g., @username)")
    parser.add_argument("--name", required=True, help="Display name")
    parser.add_argument("--niche", required=True, help="Niche")
    parser.add_argument("--positioning", required=True, help="Positioning one-liner")
    parser.add_argument("--target-audience", required=True, help="Target audience")
    parser.add_argument("--voice", required=True, help="Voice/tone")

    args = parser.parse_args()

    print("=" * 60)
    print("CREATE NEW ACCOUNT")
    print("=" * 60)
    print()
    print(f"Account ID: {args.account_id}")
    print(f"Username: {args.username}")
    print(f"Name: {args.name}")
    print(f"Niche: {args.niche}")
    print()
    print("Creating account with AI-generated prompts...")
    print()

    create_account(
        args.account_id,
        args.username,
        args.name,
        args.niche,
        args.positioning,
        args.target_audience,
        args.voice,
    )
