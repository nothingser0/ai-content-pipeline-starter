"""
Diff tool for comparing content versions
Provides side-by-side comparison with highlighted changes
"""

import difflib

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class DiffTool:
    """Tool for comparing content versions"""
    
    @staticmethod
    def compare_versions(
        content1: str,
        content2: str,
        label1: str = "Version 1",
        label2: str = "Version 2",
        context_lines: int = 3
    ) -> str:
        """
        Generate side-by-side diff between two content versions
        
        Args:
            content1: First version content
            content2: Second version content
            label1: Label for first version
            label2: Label for second version
            context_lines: Number of context lines around changes
            
        Returns:
            Formatted diff output
        """
        lines1 = content1.splitlines(keepends=True)
        lines2 = content2.splitlines(keepends=True)
        
        # Generate unified diff
        diff = difflib.unified_diff(
            lines1,
            lines2,
            fromfile=label1,
            tofile=label2,
            lineterm="",
            n=context_lines
        )
        
        return "".join(diff)
    
    @staticmethod
    def compare_side_by_side(
        content1: str,
        content2: str,
        label1: str = "Version 1",
        label2: str = "Version 2",
        width: int = 80
    ) -> str:
        """
        Generate side-by-side comparison
        
        Args:
            content1: First version content
            content2: Second version content
            label1: Label for first version
            label2: Label for second version
            width: Column width for each side
            
        Returns:
            Side-by-side formatted output
        """
        lines1 = content1.splitlines()
        lines2 = content2.splitlines()
        
        # Use HtmlDiff for side-by-side (we'll format as text)
        differ = difflib.Differ()
        diff = list(differ.compare(lines1, lines2))
        
        output = []
        output.append("=" * (width * 2 + 3))
        output.append(f"{label1:<{width}} | {label2:<{width}}")
        output.append("=" * (width * 2 + 3))
        
        i = 0
        while i < len(diff):
            line = diff[i]
            prefix = line[:2]
            content = line[2:]
            
            if prefix == "  ":  # Unchanged
                left = content[:width]
                right = content[:width]
                output.append(f"{left:<{width}} | {right:<{width}}")
            elif prefix == "- ":  # Removed from v1
                left = f"[-] {content}"[:width]
                # Check if next line is addition
                if i + 1 < len(diff) and diff[i + 1][:2] == "+ ":
                    right = f"[+] {diff[i + 1][2:]}"[:width]
                    i += 1
                else:
                    right = ""
                output.append(f"{left:<{width}} | {right:<{width}}")
            elif prefix == "+ ":  # Added to v2
                left = ""
                right = f"[+] {content}"[:width]
                output.append(f"{left:<{width}} | {right:<{width}}")
            elif prefix == "? ":  # Hint line (skip)
                pass
            
            i += 1
        
        output.append("=" * (width * 2 + 3))
        return "\n".join(output)
    
    @staticmethod
    def get_change_summary(content1: str, content2: str) -> dict[str, int]:
        """
        Get summary statistics of changes
        
        Args:
            content1: First version content
            content2: Second version content
            
        Returns:
            Dict with added, removed, modified line counts
        """
        lines1 = content1.splitlines()
        lines2 = content2.splitlines()
        
        matcher = difflib.SequenceMatcher(None, lines1, lines2)
        
        added = 0
        removed = 0
        modified = 0
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                modified += max(i2 - i1, j2 - j1)
            elif tag == "delete":
                removed += i2 - i1
            elif tag == "insert":
                added += j2 - j1
        
        return {
            "added": added,
            "removed": removed,
            "modified": modified,
            "total_changes": added + removed + modified
        }
    
    @staticmethod
    def format_diff_output(
        content1: str,
        content2: str,
        label1: str = "Version 1",
        label2: str = "Version 2",
        show_summary: bool = True
    ) -> str:
        """
        Format complete diff output with summary
        
        Args:
            content1: First version content
            content2: Second version content
            label1: Label for first version
            label2: Label for second version
            show_summary: Include change summary
            
        Returns:
            Complete formatted diff
        """
        output = []
        
        if show_summary:
            summary = DiffTool.get_change_summary(content1, content2)
            output.append(f"CHANGE SUMMARY: {label1} → {label2}")
            output.append(f"  Added lines: {summary['added']}")
            output.append(f"  Removed lines: {summary['removed']}")
            output.append(f"  Modified lines: {summary['modified']}")
            output.append(f"  Total changes: {summary['total_changes']}")
            output.append("")
        
        # Add unified diff
        output.append(DiffTool.compare_versions(content1, content2, label1, label2))
        
        return "\n".join(output)


__all__ = ["DiffTool"]
