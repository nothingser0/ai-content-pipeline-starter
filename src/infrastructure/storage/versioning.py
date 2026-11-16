"""
Content versioning system with rollback capability
Stores last 5 versions per topic with metadata
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class VersioningSystem:
    """Manages content versions with rollback capability"""
    
    MAX_VERSIONS = 5  # Keep last 5 versions per topic
    
    def __init__(self, account_id: str, output_dir: Optional[Path] = None):
        """
        Initialize versioning system
        
        Args:
            account_id: Account identifier
            output_dir: Base output directory (defaults to output/{account_id})
        """
        self.account_id = account_id
        self.output_dir = output_dir or Path("output") / account_id
        self.versions_dir = self.output_dir / ".versions"
        self.metadata_file = self.versions_dir / "versions.json"
        self.enabled = os.getenv("ENABLE_VERSIONING", "0") == "1"
        
        if self.enabled:
            self.versions_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_metadata(self) -> dict[str, Any]:
        """Load version metadata from JSON"""
        if not self.metadata_file.exists():
            return {}
        
        try:
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load version metadata: {e}")
            return {}
    
    def _save_metadata(self, metadata: dict[str, Any]) -> None:
        """Save version metadata to JSON"""
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save version metadata: {e}")
    
    def _get_topic_key(self, topic: str) -> str:
        """Normalize topic to use as metadata key"""
        return topic.lower().replace(" ", "_")[:50]
    
    def save_version(
        self,
        topic: str,
        content: str,
        qc_score: float,
        model: str = "unknown"
    ) -> Optional[str]:
        """
        Save new version of content
        
        Args:
            topic: Content topic
            content: Full content text
            qc_score: Quality control score
            model: Model used for generation
            
        Returns:
            Version identifier (e.g., "v3") or None if versioning disabled
        """
        if not self.enabled:
            return None
        
        topic_key = self._get_topic_key(topic)
        metadata = self._load_metadata()
        
        # Get existing versions for this topic
        topic_versions = metadata.get(topic_key, [])
        
        # Determine next version number
        if topic_versions:
            last_version = max(int(v["version"].replace("v", "")) for v in topic_versions)
            version_num = last_version + 1
        else:
            version_num = 1
        
        version_id = f"v{version_num}"
        
        # Save versioned file
        version_file = self.versions_dir / f"{topic_key}_{version_id}_final.md"
        try:
            version_file.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save version file: {e}")
            return None
        
        # Add version metadata
        version_entry = {
            "version": version_id,
            "timestamp": datetime.now().isoformat(),
            "qc_score": qc_score,
            "model": model,
            "file": str(version_file.relative_to(self.output_dir))
        }
        topic_versions.append(version_entry)
        
        # Keep only last MAX_VERSIONS
        if len(topic_versions) > self.MAX_VERSIONS:
            # Remove oldest version file
            old_version = topic_versions.pop(0)
            old_file = self.output_dir / old_version["file"]
            if old_file.exists():
                old_file.unlink()
        
        metadata[topic_key] = topic_versions
        self._save_metadata(metadata)
        
        # Update current symlink
        self._update_current_link(topic_key, version_file)
        
        logger.info(f"Saved version {version_id} for topic '{topic}' (QC: {qc_score:.1f})")
        return version_id
    
    def _update_current_link(self, topic_key: str, version_file: Path) -> None:
        """Update 'current' symlink to point to latest version"""
        current_link = self.versions_dir / f"{topic_key}_current.md"
        
        # Remove existing symlink/file
        if current_link.exists() or current_link.is_symlink():
            current_link.unlink()
        
        # Create new symlink (Windows: requires admin or dev mode)
        try:
            # Use relative path for portability
            rel_path = version_file.relative_to(self.versions_dir)
            current_link.symlink_to(rel_path)
        except (OSError, NotImplementedError):
            # Fallback: copy file instead of symlink
            shutil.copy2(version_file, current_link)
    
    def list_versions(self, topic: str) -> list[dict[str, Any]]:
        """
        List all versions for a topic
        
        Args:
            topic: Content topic
            
        Returns:
            List of version metadata dicts
        """
        # Allow listing even if versioning disabled (read-only)
        topic_key = self._get_topic_key(topic)
        metadata = self._load_metadata()
        return metadata.get(topic_key, [])
    
    def get_version_content(self, topic: str, version: str) -> Optional[str]:
        """
        Get content of specific version
        
        Args:
            topic: Content topic
            version: Version identifier (e.g., "v2")
            
        Returns:
            Version content or None if not found
        """
        # Allow reading even if versioning disabled (read-only)
        topic_key = self._get_topic_key(topic)
        version_file = self.versions_dir / f"{topic_key}_{version}_final.md"
        
        if not version_file.exists():
            return None
        
        try:
            return version_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read version file: {e}")
            return None
    
    def rollback(self, topic: str, version: str, output_file: Path) -> bool:
        """
        Rollback to specific version
        
        Args:
            topic: Content topic
            version: Version identifier (e.g., "v2")
            output_file: Target output file path
            
        Returns:
            True if rollback successful
        """
        # Allow rollback even if versioning disabled (read-only operation)
        content = self.get_version_content(topic, version)
        if content is None:
            logger.error(f"Version {version} not found for topic '{topic}'")
            return False
        
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(content, encoding="utf-8")
            logger.info(f"Rolled back to {version} for topic '{topic}'")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback: {e}")
            return False
    
    def get_latest_version(self, topic: str) -> Optional[str]:
        """Get latest version identifier for topic"""
        versions = self.list_versions(topic)
        if not versions:
            return None
        return versions[-1]["version"]


__all__ = ["VersioningSystem"]
