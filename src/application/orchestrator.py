"""
Pipeline Orchestrator - Main content generation pipeline logic
"""

import asyncio
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.application.services.engagement_ai import call_engagement_ai
from src.application.services.package import build_package_text, create_final_package
from src.application.services.qc_autofix import quality_check_and_fix
from src.application.services.visual_ai import call_visual_ai, parse_thread_image_briefs
from src.application.services.writer import generate_content
from src.domain.exceptions import CircuitBreakerOpenError, RetryBudgetExhaustedError
from src.infrastructure.monitoring.metrics import (
    record_content_generated,
    record_generation_duration,
    record_qc_score,
)
from src.infrastructure.resilience.fallback_cache import get_fallback_cache
from src.infrastructure.utils.engagement_prompt import generate_engagement_prompt

AccountConfig = dict[str, Any]
AngleData = dict[str, Any]


class PipelineOrchestrator:
    """Orchestrates the full content generation pipeline"""

    def __init__(
        self,
        account_id: str,
        account_config: AccountConfig,
        accounts_path: Path,
    ):
        self.account_id = account_id
        self.account_config = account_config
        self.accounts_path = accounts_path

    async def run(
        self,
        topic: str,
        angle: AngleData,
        content_format: str,
        writer_prompt: str,
    ) -> dict[str, Any]:
        """
        Run the full content generation pipeline

        Args:
            topic: Content topic
            angle: Selected angle data
            content_format: Content format (Single Tweet, Thread, Poll, Image)
            writer_prompt: Account-specific writer prompt

        Returns:
            Package data dict with all generated content

        Raises:
            CircuitBreakerOpenError: If circuit breaker is open
            RetryBudgetExhaustedError: If retry budget exhausted
        """
        start_time = time.time()

        try:
            # Step 1: Generate content
            print(f"\nGenerating {content_format} content...")
            content = await generate_content(
                angle_data=angle,
                format_choice=content_format,
                writer_prompt=writer_prompt,
                account_config=self.account_config,
            )

            if not content:
                raise RuntimeError("Failed to generate content")

            # Step 2: Quality check and auto-fix
            print("\nRunning quality check...")
            qc_result = await quality_check_and_fix(
                content=content,
                angle=angle,
                format_type=content_format,
                enable_autofix=True,
                account_config=self.account_config,
            )

            # Show QC results
            if qc_result.get("autofix_applied"):
                print("🔧 QC issues detected - autofix applied")

            if not qc_result.get("passed") and qc_result.get("issues"):
                print(f"⚠️  QC issues remaining: {', '.join(qc_result['issues'])}")

            # Step 3: Visual generation (format-specific logic)
            enable_visual_env = os.getenv("ENABLE_VISUAL", "1").strip().lower()
            visual_feature_enabled = enable_visual_env not in ("0", "false", "no", "off")

            visual_brief = None
            should_generate_visual = False
            visual_probability = "0% (Disabled)"
            visual_type = None
            thread_images = None

            if not visual_feature_enabled:
                print("\n🖼️ Visual generation: Disabled (ENABLE_VISUAL=0)")
            elif content_format == "Image":
                should_generate_visual = True
                visual_probability = "100%"
                visual_type = "slides"
                print("\n🖼️ Visual generation: Yes (100% - slides)")
            elif content_format == "Thread":
                should_generate_visual = True
                visual_probability = "100%"
                visual_type = "slides"  # Generate header + additional images for tweets
                print("\n🖼️ Visual generation: Yes (100% - header + additional tweets)")
            elif content_format in ["Single Tweet", "Poll"]:
                should_generate_visual = random.random() < 0.6
                visual_probability = "60%"
                visual_type = "single"
                if should_generate_visual:
                    print("\n🖼️ Visual generation: Yes (60% chance - single)")
                else:
                    print("\n🖼️ Visual generation: Skipped (40% chance)")

            # Step 4: Run visual and engagement generation in parallel
            visual_task = None
            engagement_task = None

            if should_generate_visual:
                print("\nGenerating visual brief...")
                visual_task = call_visual_ai(
                    content=qc_result.get("fixed_content", content),
                    format_type=content_format,
                    visual_type=visual_type or "single",
                    account_id=self.account_id,
                )

            enable_engagement_env = os.getenv("ENABLE_ENGAGEMENT", "1").strip().lower()
            engagement_feature_enabled = enable_engagement_env not in ("0", "false", "no", "off")

            if not engagement_feature_enabled:
                print("\n🤝 Engagement strategy: Disabled (ENABLE_ENGAGEMENT=0)")
            else:
                print("\nGenerating engagement strategy...")
                engagement_prompt = generate_engagement_prompt(self.account_config)
                engagement_task = call_engagement_ai(
                    content=qc_result.get("fixed_content", content),
                    format_type=content_format,
                    engagement_prompt=engagement_prompt,
                    account_config=self.account_config,
                )

            # Gather results in parallel
            tasks = []
            if visual_task:
                tasks.append(visual_task)
            if engagement_task:
                tasks.append(engagement_task)

            results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []

            # Process results
            result_idx = 0
            engagement_strategy = None

            if visual_task:
                visual_result = results[result_idx]
                result_idx += 1
                if isinstance(visual_result, Exception):
                    print(f"⚠️  Visual brief generation failed: {visual_result}")
                    visual_brief = None
                elif isinstance(visual_result, str):
                    visual_brief = visual_result
                    print("✅ Visual brief generated")

                    # For Thread format, parse multiple image briefs
                    if content_format == "Thread":
                        thread_images = parse_thread_image_briefs(visual_brief)
                        if thread_images:
                            image_count = len(thread_images)
                            tweet_positions = sorted(thread_images.keys())
                            print(
                                f"   Thread images: {image_count} (tweets: {', '.join(map(str, tweet_positions))})"
                            )
                else:
                    visual_brief = None

            if engagement_task:
                engagement_result = results[result_idx]
                if isinstance(engagement_result, Exception):
                    print(
                        f"⚠️  Engagement strategy generation failed: {engagement_result}"
                    )
                    engagement_strategy = None
                elif isinstance(engagement_result, str):
                    engagement_strategy = engagement_result
                    print("✅ Engagement strategy generated")
                else:
                    engagement_strategy = None

            # Step 5: Build package data
            package_data = {
                "account": self.account_config,
                "topic": topic,
                "angle": angle,
                "format": content_format,
                "content": qc_result.get("fixed_content", content),
                "qc": qc_result,
                "visual_brief": visual_brief,
                "visual_probability": visual_probability,
                "visual_generated": should_generate_visual and bool(visual_brief),
                "visual_type": visual_type if should_generate_visual else None,
                "thread_images": thread_images,
                "engagement_strategy": engagement_strategy,
            }

            # Record metrics
            elapsed = time.time() - start_time
            qc_score = qc_result.get("overall_score", 0)
            record_generation_duration(self.account_id, content_format, elapsed)
            record_qc_score(self.account_id, content_format, qc_score)
            record_content_generated(self.account_id, content_format, "success")

            # Store in fallback cache for circuit breaker recovery
            try:
                redis_url = os.getenv("REDIS_URL")
                fallback_cache = await get_fallback_cache(redis_url)
                await fallback_cache.store(
                    account_id=self.account_id,
                    content=qc_result.get("fixed_content", content),
                    qc_score=qc_score,
                    format=content_format,
                )
            except Exception as cache_error:
                # Don't fail pipeline if cache storage fails
                print(f"⚠️  Failed to store in fallback cache: {cache_error}")

            print(f"QC Score: {qc_score}/10")
            if qc_result.get("issues"):
                print("QC Issues:")
                for issue in qc_result["issues"]:
                    print(f"- {issue}")

            return package_data

        except (CircuitBreakerOpenError, RetryBudgetExhaustedError) as e:
            print(f"\n✗ Pipeline failed: {e}")
            raise
        except Exception as e:
            print(f"\n✗ Pipeline failed: {e}")
            raise
