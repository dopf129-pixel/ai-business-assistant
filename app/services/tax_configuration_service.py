import json
import math
import os
import tempfile

from services.tax_service import TaxService


class TaxConfigurationService:

    def __init__(
        self,
        file_path=None,
        environment=None
    ):
        self.file_path = (
            file_path
            or os.path.join(
                os.getcwd(),
                "data",
                "tax_configuration.json"
            )
        )
        self.environment = (
            os.environ
            if environment is None
            else environment
        )

    def get_policy(self):
        if not os.path.exists(self.file_path):
            return self._get_environment_policy()

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


    def _get_environment_policy(self):
        mode = self.environment.get(
            "TAX_MODE"
        )

        if (
            mode is None
            or not str(mode).strip()
        ):
            return {
                "error": False,
                "configured": False,
                "policy": None
            }

        validated = self._validate_policy(
            {
                "mode": mode,
                "tax_rate": self.environment.get(
                    "TAX_RATE"
                ),
                "minimum_tax_rate": (
                    self.environment.get(
                        "MINIMUM_TAX_RATE",
                        1.0
                    )
                )
            }
        )

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
        temp_path = None

        try:
            serialized = json.dumps(
                validated["policy"],
                ensure_ascii=False,
                indent=4,
                allow_nan=False
            )

            if folder:
                os.makedirs(
                    folder,
                    exist_ok=True
                )

            fd, temp_path = tempfile.mkstemp(
                prefix=".tax-configuration-write-",
                suffix=".tmp",
                dir=(folder or ".")
            )

            with os.fdopen(
                fd,
                "w",
                encoding="utf-8"
            ) as file:
                file.write(serialized)
                file.flush()
                os.fsync(file.fileno())

            os.replace(
                temp_path,
                self.file_path
            )
            temp_path = None

        except Exception:
            self._cleanup_temp(temp_path)
            return {
                "error": True,
                "saved": False,
                "message": "TAX_CONFIGURATION_SAVE_FAILED"
            }

        return {
            "error": False,
            "saved": True,
            "atomic_replace": True,
            "policy": validated["policy"]
        }

    def _validate_policy(self, policy):
        if not isinstance(policy, dict):
            return {
                "error": True,
                "message": "Некорректная налоговая конфигурация"
            }

        mode = str(
            policy.get("mode") or ""
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
            tax_rate = policy.get("tax_rate")

            if tax_rate is None:
                return {
                    "error": True,
                    "message": "Не указана налоговая ставка"
                }

            normalized_tax_rate = self._normalize_rate(
                tax_rate
            )

            if normalized_tax_rate is None:
                return {
                    "error": True,
                    "message": "Некорректная налоговая ставка"
                }

            normalized_minimum_tax_rate = (
                self._normalize_rate(
                    policy.get(
                        "minimum_tax_rate",
                        1.0
                    )
                )
            )

            if normalized_minimum_tax_rate is None:
                return {
                    "error": True,
                    "message": (
                        "Некорректная минимальная налоговая ставка"
                    )
                }

            normalized = {
                "mode": mode,
                "tax_rate": normalized_tax_rate,
                "minimum_tax_rate": (
                    normalized_minimum_tax_rate
                )
            }

        return {
            "error": False,
            "policy": normalized
        }

    @staticmethod
    def _normalize_rate(value):
        if isinstance(value, bool):
            return None

        try:
            rate = float(value)
        except (
            TypeError,
            ValueError
        ):
            return None

        if (
            not math.isfinite(rate)
            or rate < 0.0
            or rate > 100.0
        ):
            return None

        return rate

    @staticmethod
    def _cleanup_temp(temp_path):
        if not temp_path:
            return

        try:
            os.unlink(temp_path)
        except Exception:
            return
