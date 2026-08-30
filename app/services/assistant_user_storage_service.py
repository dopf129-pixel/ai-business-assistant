import json
import os
import tempfile


class AssistantUserStorageService:

    def __init__(
        self,
        file_path=None
    ):

        if file_path is None:

            file_path = os.path.join(
                os.getcwd(),
                "data",
                "users.json"
            )

        self.file_path = file_path
        self.users = {}
        self.load_state = "UNINITIALIZED"
        self.load_issue = None

        self.load()


    def normalize_id(
        self,
        user_id
    ):

        return str(
            user_id
        )


    def load(
        self
    ):

        if not os.path.exists(
            self.file_path
        ):

            self.users = {}
            self.load_state = "ABSENT"
            self.load_issue = None

            return {
                "error": False,
                "state": "ABSENT"
            }

        try:

            with open(
                self.file_path,
                "r",
                encoding="utf-8"
            ) as file:

                loaded = json.load(
                    file
                )

        except Exception:

            self.users = {}
            self.load_state = "ERROR"
            self.load_issue = (
                "USER_STORAGE_LOAD_FAILED"
            )

            return self._unavailable_result()

        if not isinstance(
            loaded,
            dict
        ):

            self.users = {}
            self.load_state = "ERROR"
            self.load_issue = (
                "USER_STORAGE_ROOT_INVALID"
            )

            return self._unavailable_result()

        self.users = loaded
        self.load_state = "LOADED"
        self.load_issue = None

        return {
            "error": False,
            "state": "LOADED"
        }


    def save(
        self
    ):

        if self.load_state == "ERROR":

            return self._unavailable_result()

        folder = os.path.dirname(
            self.file_path
        )

        try:

            serialized = json.dumps(
                self.users,
                ensure_ascii=False,
                indent=4
            )

        except Exception:

            return {
                "error": True,
                "message":
                    "USER_STORAGE_SERIALIZATION_FAILED"
            }

        temp_path = None
        replaced = False

        try:

            if (
                folder
                and not os.path.exists(
                    folder
                )
            ):

                os.makedirs(
                    folder
                )

            target_folder = (
                folder
                or "."
            )

            fd, temp_path = (
                tempfile.mkstemp(
                    prefix=
                        ".users-write-",
                    suffix=".tmp",
                    dir=target_folder
                )
            )

            with os.fdopen(
                fd,
                "w",
                encoding="utf-8"
            ) as file:

                file.write(
                    serialized
                )

                file.flush()
                os.fsync(
                    file.fileno()
                )

            os.replace(
                temp_path,
                self.file_path
            )

            replaced = True
            temp_path = None

        except Exception:

            self._cleanup_temp(
                temp_path
            )

            return {
                "error": True,
                "message":
                    "USER_STORAGE_SAVE_FAILED"
            }

        if self.load_state == "ABSENT":
            self.load_state = "LOADED"

        durability_warning = (
            self._fsync_directory(
                folder
                or "."
            )
            is False
        )

        result = {
            "error": False,
            "saved": True,
            "atomic_replace": (
                replaced
            )
        }

        if durability_warning:

            result[
                "durability_warning"
            ] = (
                "USER_STORAGE_DIRECTORY_FSYNC_FAILED"
            )

        return result


    def create_user(
        self,
        user_id
    ):

        if self.load_state == "ERROR":

            return self._unavailable_result()

        user_id = self.normalize_id(
            user_id
        )

        if user_id in self.users:

            existing = self.users[
                user_id
            ]

            if not self._valid_user(
                existing,
                user_id
            ):

                return {
                    "error": True,
                    "message":
                        "USER_STORAGE_USER_INVALID"
                }

            return {
                "error": False,
                "user": existing
            }

        user = {
            "user_id": user_id,
            "memory": {},
            "history": []
        }

        self.users[user_id] = user

        save_result = self.save()

        if save_result.get(
            "error"
        ):

            self.users.pop(
                user_id,
                None
            )

            return save_result

        return {
            "error": False,
            "user": user
        }


    def get_user(
        self,
        user_id
    ):

        return (
            self.create_user(
                user_id
            )
        )


    def save_memory(
        self,
        user_id,
        key,
        value
    ):

        user_result = (
            self.create_user(
                user_id
            )
        )

        if user_result.get(
            "error"
        ):

            return user_result

        user = user_result[
            "user"
        ]

        memory = user.get(
            "memory"
        )

        if not isinstance(
            memory,
            dict
        ):

            return {
                "error": True,
                "message":
                    "USER_STORAGE_MEMORY_INVALID"
            }

        existed = key in memory
        previous = memory.get(
            key
        )

        memory[key] = value

        save_result = self.save()

        if save_result.get(
            "error"
        ):

            if existed:
                memory[key] = previous
            else:
                memory.pop(
                    key,
                    None
                )

            return save_result

        return {
            "error": False,
            "saved": True
        }


    def get_memory(
        self,
        user_id
    ):

        user_result = (
            self.create_user(
                user_id
            )
        )

        if user_result.get(
            "error"
        ):

            return user_result

        memory = user_result[
            "user"
        ].get(
            "memory"
        )

        if not isinstance(
            memory,
            dict
        ):

            return {
                "error": True,
                "message":
                    "USER_STORAGE_MEMORY_INVALID"
            }

        return {
            "error": False,
            "memory": memory
        }


    def add_history(
        self,
        user_id,
        event
    ):

        user_result = (
            self.create_user(
                user_id
            )
        )

        if user_result.get(
            "error"
        ):

            return user_result

        user = user_result[
            "user"
        ]

        history = user.get(
            "history"
        )

        if not isinstance(
            history,
            list
        ):

            return {
                "error": True,
                "message":
                    "USER_STORAGE_HISTORY_INVALID"
            }

        history.append(
            event
        )

        save_result = self.save()

        if save_result.get(
            "error"
        ):

            history.pop()

            return save_result

        return {
            "error": False,
            "saved": True
        }


    def get_history(
        self,
        user_id
    ):

        user_result = (
            self.create_user(
                user_id
            )
        )

        if user_result.get(
            "error"
        ):

            return user_result

        history = user_result[
            "user"
        ].get(
            "history"
        )

        if not isinstance(
            history,
            list
        ):

            return {
                "error": True,
                "message":
                    "USER_STORAGE_HISTORY_INVALID"
            }

        return {
            "error": False,
            "history": history
        }


    @staticmethod
    def _valid_user(
        user,
        expected_user_id
    ):

        return (
            isinstance(
                user,
                dict
            )
            and user.get(
                "user_id"
            )
            == expected_user_id
            and "memory" in user
            and isinstance(
                user.get(
                    "memory"
                ),
                dict
            )
            and "history" in user
            and isinstance(
                user.get(
                    "history"
                ),
                list
            )
        )


    def _unavailable_result(
        self
    ):

        return {
            "error": True,
            "message":
                self.load_issue
                or "USER_STORAGE_UNAVAILABLE"
        }


    @staticmethod
    def _cleanup_temp(
        temp_path
    ):

        if not temp_path:
            return

        try:
            os.unlink(
                temp_path
            )
        except Exception:
            return


    @staticmethod
    def _fsync_directory(
        directory
    ):

        flags = os.O_RDONLY

        if hasattr(
            os,
            "O_DIRECTORY"
        ):
            flags = (
                flags
                | os.O_DIRECTORY
            )

        try:

            fd = os.open(
                directory,
                flags
            )

        except Exception:

            return False

        try:

            os.fsync(
                fd
            )

        except Exception:

            return False

        finally:

            try:
                os.close(
                    fd
                )
            except Exception:
                pass

        return True