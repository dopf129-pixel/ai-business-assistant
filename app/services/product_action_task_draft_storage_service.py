from services.product_decision_history_storage_service import (
    ProductDecisionHistoryStorageService
)


class ProductActionTaskDraftStorageService(
    ProductDecisionHistoryStorageService
):

    DEFAULT_FILE_PATH = "data/product_action_task_drafts.json"

    def __init__(self, file_path=None):
        super().__init__(file_path=file_path)
