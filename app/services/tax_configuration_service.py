import json
import os

from services.tax_service import TaxService


class TaxConfigurationService:

    def __init__(self, file_path=None):
        self.file_path = (
            file_path
            or os.path.join(
                os.getcwd(),
                "data",
                "tax_configuration.json"
            )
        )

    def get_policy(self):
        if not os.path.exists(self.file_path):
            return {
                "error": False,
                "configured": False,
                "policy": None
            }

        try:
            with open(
                self.file_path,
                "r",
                encoding="utf-8"
            ) as file:
                policy = json.load(file)
        except Exception:
            return {
                "error": False,
                "configured": False,
                "policy": None
            }

        validated = self._validate_policy(policy)

        if validated.get("error"):
            return {
                "error": False,
                "configured": False,
                "policy": None
            }

        return {
            "error": False,
            "configured": True,
            "policy": validated["policy"]
        }

    def save_policy(
        self,
        mode,
        tax_rate=None,
        minimum_tax_rate=1.0
    ):
        validated = self._validate_policy(
            {
                "mode": mode,
                "tax_rate": tax_rate,
                "minimum_tax_rate": minimum_tax_rate
            }
        )

        if validated.get("error"):
            return validated

        folder = os.path.dirname(self.file_path)

        if folder:
            os.makedirs(folder, exist_ok=True)

        with open(
            self.file_path,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                validated["policy"],
                file,
                ensure_ascii=False,
                indent=4
            )

        return {
            "error": False,
            "saved": True,
            "policy": validated["policy"]
        }

    def _validate_policy(self, policy):
        mode = str(
            (policy or {}).get("mode") or ""
        ).upper()

        if mode not in TaxService.SUPPORTED_MODES:
            return {
                "error": True,
                "message": "Неподдерживаемый налоговый режим"
            }

        if mode == "NONE":
            normalized = {
                "mode": "NONE",
                "tax_rate": 0.0,
                "minimum_tax_rate": 0.0
            }
        else:
            tax_rate = (policy or {}).get("tax_rate")

            if tax_rate is None:
                return {
                    "error": True,
                    "message": "Не указана налоговая ставка"
                }

            normalized = {
                "mode": mode,
                "tax_rate": float(tax_rate),
                "minimum_tax_rate": float(
                    (policy or {}).get(
                        "minimum_tax_rate",
                        1.0
                    )
                )
            }

        return {
            "error": False,
            "policy": normalized
        }
