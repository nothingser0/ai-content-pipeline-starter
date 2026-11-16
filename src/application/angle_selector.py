"""
Angle Selector - Angle selection and display logic
"""

from typing import Any

AngleData = dict[str, Any]


def auto_select_angle(angles: list[AngleData]) -> AngleData:
    """
    Auto-select angle with highest combined value + viral score

    Args:
        angles: List of angle data dicts

    Returns:
        Selected angle with highest score
    """
    return max(
        angles,
        key=lambda angle: angle.get("value_score", 0) + angle.get("viral_score", 0),
    )


def display_angles(angles: list[AngleData]) -> None:
    """
    Display angles in formatted list

    Args:
        angles: List of angle data dicts
    """
    print("\n[2/4] Generated angles:")
    for idx, angle in enumerate(angles, 1):
        title = angle.get("title", "Untitled")
        value_score = angle.get("value_score", 0)
        viral_score = angle.get("viral_score", 0)
        total_score = value_score + viral_score
        print(f"{idx}. {title} (Value: {value_score}, Viral: {viral_score}, Total: {total_score})")


def select_angle_interactive(angles: list[AngleData]) -> AngleData:
    """
    Let user pick angle interactively or auto-select

    Args:
        angles: List of angle data dicts

    Returns:
        Selected angle
    """
    display_angles(angles)
    print("\n[3/4] Select angle:")
    choice = input("Enter number (1-10) or 0 for auto-select: ").strip()

    if choice == "0":
        selected = auto_select_angle(angles)
        print(f"Auto-selected: {selected.get('title', 'Untitled')}")
        return selected

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(angles):
            return angles[idx]
        else:
            print("Invalid choice, auto-selecting...")
            return auto_select_angle(angles)
    except ValueError:
        print("Invalid input, auto-selecting...")
        return auto_select_angle(angles)


class AngleSelector:
    """Handles angle selection logic"""

    def __init__(self, angles: list[AngleData]):
        self.angles = angles

    def select(self, interactive: bool = False) -> AngleData:
        """
        Select angle (interactive or auto)

        Args:
            interactive: If True, prompt user for selection

        Returns:
            Selected angle
        """
        if interactive:
            return select_angle_interactive(self.angles)
        else:
            selected = auto_select_angle(self.angles)
            print(f"\n[3/4] Auto-selected angle: {selected.get('title', 'Untitled')}")
            return selected

    def display(self) -> None:
        """Display all angles"""
        display_angles(self.angles)
