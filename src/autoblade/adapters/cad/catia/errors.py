"""CATIA Adapter 的能力错误。"""


from ....core.backend import BackendError, BackendName


class CatiaBackendUnavailableError(BackendError):
    """当前平台或 Python 环境无法装载 CATIA COM 后端。"""

    def __init__(self, message: str) -> None:
        super().__init__(BackendName.CATIA, "unavailable", message)
