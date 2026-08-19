class AssistantChangeImpactService:
    """
    Analyzes development change impact.

    Provides recommendations for:
    - tests
    - documentation
    - validation
    """

    def analyze_change(self, files):
        """
        Analyzes changed files.
        """

        impact = {
            "files": files,
            "tests_required": [],
            "documentation_required": [],
        }

        for file in files:

            if file.startswith("app/services/"):
                service_name = (
                    file
                    .replace("app/services/", "")
                    .replace(".py", "")
                )

                impact["tests_required"].append(
                    f"tests/test_{service_name}.py"
                )

                impact["documentation_required"].extend(
                    [
                        "project_brain/TEST_MAP.md",
                        "project_brain/CHANGELOG.md",
                    ]
                )

        return impact
