from pathlib import Path
from datetime import date


class AssistantDocumentationManager:
    """
    Development Autopilot documentation layer.

    Responsible for safe Project Brain updates.
    """

    def __init__(self, project_root="."):
        self.project_root = Path(project_root)
        self.brain_path = self.project_root / "project_brain"

    def append_changelog(self, title: str, content: str):
        """
        Append new changelog entry.
        CHANGELOG.md is append-only.
        """

        changelog = self.brain_path / "CHANGELOG.md"

        entry = f"""

---

## Added

### {title}


Date:

{date.today()}


{content}

"""

        with changelog.open("a", encoding="utf-8") as file:
            file.write(entry)


    def append_decision(self, title: str, content: str):
        """
        Append architecture decision.
        """

        decisions = self.brain_path / "DECISIONS.md"

        entry = f"""

---

## Decision


Date:

{date.today()}


Topic:

{title}


{content}

"""

        with decisions.open("a", encoding="utf-8") as file:
            file.write(entry)