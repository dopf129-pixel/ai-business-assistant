from pathlib import Path
from datetime import date


class AssistantProjectBrainManager:
    """
    Manages safe Project Brain updates.

    Rules:
    - append only
    - preserve history
    - no destructive changes
    """

    def __init__(self, project_root="."):
        self.root = Path(project_root)

        self.brain = (
            self.root / "project_brain"
        )


    def append_to_file(self, filename, content):
        """
        Safely appends content.
        """

        path = self.brain / filename

        with path.open(
            "a",
            encoding="utf-8"
        ) as file:
            file.write(content)


    def add_changelog_entry(
        self,
        title,
        description,
    ):
        entry = f"""

---

## Added


### {title}


Date:

{date.today()}


{description}

"""

        self.append_to_file(
            "CHANGELOG.md",
            entry,
        )


    def add_test_map_entry(
        self,
        service,
        test,
    ):
        entry = f"""

---

Service:

{service}


Tests:

- {test}

"""

        self.append_to_file(
            "TEST_MAP.md",
            entry,
        )