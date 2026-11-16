#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Engagement Prompt Template Generator
Generates account-specific engagement strategy prompts
"""


def generate_engagement_prompt(account_config: dict) -> str:
    """
    Generate comprehensive engagement prompt from account config

    Args:
        account_config: Account configuration dict with engagement fields

    Returns:
        Formatted engagement prompt string
    """

    # Extract base fields
    username = account_config.get("username", "@unknown")
    niche = account_config.get("niche", "General")
    target_audience = account_config.get("target_audience", "")
    timezone = account_config.get("timezone", "UTC")

    # Extract engagement fields
    posting_times = account_config.get("posting_times", {})
    hashtag_strategy = account_config.get("hashtag_strategy", "mix_popular_niche")
    cta_style = account_config.get("cta_style", "conversational")
    platform_mix = account_config.get("platform_mix", ["Twitter"])
    engagement_examples = account_config.get("engagement_examples", {})

    # Build posting times section
    if posting_times:
        times_text = "\n".join(
            [
                f"   - {content_type.replace('_', ' ').title()} → {time}"
                for content_type, time in posting_times.items()
            ]
        )
    else:
        times_text = """   - Urgent/breaking news → Post ASAP (any time)
   - Educational/tutorial → 12:00-13:00 or 20:00-22:00 (lunch/evening)
   - Story/entertainment → 19:00-21:00 (prime time)
   - Analysis/data → 08:00-09:00 or 21:00-22:00 (before/after work)"""

    # Build hashtag strategy
    hashtag_guide = {
        "mix_popular_niche": "Mix 2-3 popular hashtags with 2-3 niche-specific hashtags",
        "niche_only": "Use only niche-specific hashtags (3-5)",
        "minimal": "Use 1-2 highly relevant hashtags only",
        "branded": "Always include brand hashtag + 2-3 content-specific",
    }.get(hashtag_strategy, "Mix popular and niche hashtags")

    # Build CTA style guide
    cta_guide = {
        "conversational": "Natural questions that invite genuine responses",
        "direct": "Clear action requests (RT, bookmark, share)",
        "minimal": "Subtle or no explicit CTA, let content speak",
        "community": "Focus on building discussion and shared experiences",
    }.get(cta_style, "Natural and conversational")

    # Build platform mix
    platforms_text = ", ".join(platform_mix)

    # Build engagement examples
    if engagement_examples:
        examples_text = "\n\n".join(
            [
                f"**{key.replace('_', ' ').title()}:**\n{value}"
                for key, value in engagement_examples.items()
            ]
        )
    else:
        examples_text = """**Good Posting Time:**
"20:30 on Wednesday - Content about scam warning. People most active reading warnings in evening when relaxed scrolling. Avoid weekends (engagement drops 40%)."

**Good Hashtags:**
"#LayerZero #AirdropAlert #L2 #Web3Security - LayerZero mentioned in content, AirdropAlert is theme, L2 is niche, Web3Security is relevant."

**Good CTA:**
"Ever experienced a rug pull? Drop project name and amount in replies so others can learn. RT to spread awareness."

**Good First Comment:**
"I lost $500 to a rug pull in 2023. Red flags I missed: anonymous team, no audit, excessive hype. What red flags have you learned to watch for?\""""

    # Generate prompt
    prompt = f"""You are an engagement strategist for {username}.

## CONTENT TO ANALYZE
{{content}}

## FORMAT
{{format_type}}

## ACCOUNT CONTEXT
- Username: {username}
- Niche: {niche}
- Audience: {target_audience}
- Timezone: {timezone}
- Primary platforms: {platforms_text}

## TASK
Generate SPECIFIC engagement strategy from analyzing THIS content. Not generic templates!

## REQUIREMENTS

### 1. POSTING TIME
Analyze content type and recommend optimal posting time:
{times_text}

Provide SPECIFIC reasoning why this time is optimal for THIS content.
Consider: content urgency, audience behavior, timezone ({timezone})

### 2. HASHTAGS
Extract keywords from actual content:
- Strategy: {hashtag_guide}
- 3-5 hashtags that are RELEVANT to this specific content
- Mix popular + niche based on content topic
- NO generic hashtags that work for any content

Example: If content about "LayerZero airdrop" → #LayerZero #AirdropAlert #L2 #[NicheTag]

### 3. CALL TO ACTION (CTA)
Create CTA that fits content naturally:
- Style: {cta_guide}
- Must emerge naturally from content, not forced
- Match account voice and audience expectations

Examples based on content type:
- Question content → "Share your experience in replies"
- Warning content → "RT so others don't get scammed"
- Tutorial content → "Bookmark to try later"
- Opinion content → "Agree or disagree? Drop your take"

### 4. FIRST COMMENT
Draft actual comment to post:
- NOT template like "Ever experienced this? Share below!"
- Specific to THIS content
- Vulnerable/authentic to encourage engagement
- Include specific details or examples

Example: If content about rug pull → "I lost $500 to a rug pull in 2023 on [Project]. Red flags I missed: [specific flags]. What about you? Share amount & project so others learn."

### 5. PLATFORM STRATEGY
Based on content type and format:
- Primary platform: {platform_mix[0] if platform_mix else 'Twitter'}
- Cross-post opportunities: {', '.join(platform_mix[1:]) if len(platform_mix) > 1 else 'None'}
- Repurpose suggestions for other platforms

Provide SPECIFIC actions for THIS content.

## GOOD OUTPUT EXAMPLES
{examples_text}

## BAD OUTPUT (AVOID)
**Generic Time:** "20:00-22:00" (no reasoning)
**Generic Hashtags:** #Crypto #Web3 #Blockchain #Bitcoin (not content-specific)
**Generic CTA:** "RT if helpful" (no context)
**Generic Comment:** "Ever experienced this? Share below!" (template)

## OUTPUT FORMAT
Return structured engagement strategy:

**POSTING TIME:** [Specific time with day preference]
**Why:** [Specific reasoning for THIS content]

**HASHTAGS:** [3-5 specific hashtags]
**Why:** [Why each hashtag is relevant to THIS content]

**CTA:** [Natural call to action]
**Why:** [Why this CTA fits THIS content]

**FIRST COMMENT:** [Actual comment text]
**Why:** [Strategy behind this comment]

**PLATFORM STRATEGY:** [Specific cross-post/repurpose actions]

Generate engagement strategy that is SPECIFIC to this content!
"""

    return prompt


# Example engagement config fields
ENGAGEMENT_CONFIG_EXAMPLE = {
    "account_id": "01-ai-automation",
    "username": "@rizkymahendrax",
    "timezone": "Asia/Jakarta",
    "posting_times": {
        "urgent": "ASAP (any time)",
        "educational": ["12:00-13:00", "20:00-22:00"],
        "entertainment": ["19:00-21:00"],
        "analysis": ["08:00-09:00", "21:00-22:00"],
    },
    "hashtag_strategy": "mix_popular_niche",  # or: niche_only, minimal, branded
    "cta_style": "conversational",  # or: direct, minimal, community
    "platform_mix": ["Twitter", "LinkedIn"],
    "engagement_examples": {
        "good_posting_time": "20:30 on Wednesday - Tool review content. People research tools in evening after work. Avoid Monday (low engagement) and weekend (B2B audience offline).",
        "good_hashtags": "#ChatGPT #AITools #Productivity #AutomationTips - ChatGPT mentioned in content, AITools is niche, Productivity is popular, AutomationTips is specific.",
        "good_cta": "What AI tool are you actually using daily? (Not what you tried once.) Drop it below.",
        "good_first_comment": "I've tested 50+ AI tools this year. Only 3 made it to my daily workflow: ChatGPT for writing, Notion AI for notes, Perplexity for research. What's in your daily stack?",
    },
}
