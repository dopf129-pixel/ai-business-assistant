from pathlib import Path


class AssistantDocumentationDriftService:
    """
    Detects simple documentation drift
    between code services and Project Brain.
    """

    def __init__(self, project_root="."):
        self.project_root = Path(project_root)

        self.services_path = (
            self.project_root
            / "app"
            / "services"
        )

        self.test_map_path = (
            self.project_root
            / "project_brain"
            / "TEST_MAP.md"
        )


    def get_services(self):
        """
        Returns service names from app/services.
        """

        if not self.services_path.exists():
            return []

        return [
            file.stem
            for file in self.services_path.glob("*.py")
            if file.stem != "__init__"
        ]


    def get_missing_documentation(self):
        """
        Finds services that are not mentioned
        in TEST_MAP.md.
        """

        if not self.test_map_path.exists():
            return self.get_services()

        content = self.test_map_path.read_text(
            encoding="utf-8"
        )

        missing = []

        for service in self.get_services():
            if service not in content:
                missing.append(service)

        return missing