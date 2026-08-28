import json
from pathlib import Path


class ProductDecisionHistoryStorageService:

    def __init__(
        self,
        file_path="data/product_decision_history.json"
    ):
        self.file_path = Path(file_path)

    def load(self):
        if not self.file_path.exists():
            return []

        try:
            with self.file_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return []

        if not isinstance(data, list):
            return []
        return [dict(item) for item in data if isinstance(item, dict)]

    def save(self, records):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.file_path.with_suffix(
            self.file_path.suffix + ".tmp"
        )
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(
                list(records or []),
                file,
                ensure_ascii=False,
                indent=2
            )
        temporary_path.replace(self.file_path)
        return True
