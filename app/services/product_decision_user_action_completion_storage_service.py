from services.product_decision_history_storage_service import ProductDecisionHistoryStorageService


class ProductDecisionUserActionCompletionStorageService(ProductDecisionHistoryStorageService):

    DEFAULT_FILE_PATH = "data/product_decision_user_action_completion.json"

    def __init__(self, file_path=None):
        super().__init__(file_path=file_path)
