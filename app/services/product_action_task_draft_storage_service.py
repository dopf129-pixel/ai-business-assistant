from services.product_decision_history_storage_service import (
    ProductDecisionHistoryStorageService
)


class ProductActionTaskDraftStorageService(
    ProductDecisionHistoryStorageService
):

    def __init__(self, file_path="data/product_action_task_drafts.json"):
        super().__init__(file_path=file_path)
