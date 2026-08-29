from services.product_decision_history_storage_service import ProductDecisionHistoryStorageService


class ProductDecisionUserActionCompletionStorageService(ProductDecisionHistoryStorageService):

    def __init__(self, file_path="data/product_decision_user_action_completion.json"):
        super().__init__(file_path=file_path)
