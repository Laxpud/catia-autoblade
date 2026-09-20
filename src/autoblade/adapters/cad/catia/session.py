import gc
from collections.abc import Callable
from typing import Any

from .errors import CatiaBackendUnavailableError
from ....core.backend import BackendError, BackendName


class CatiaCleanupError(BackendError):
    """表示建模成功后，CATIA 或 COM 资源未能完整释放。"""

    def __init__(self, message: str) -> None:
        super().__init__(BackendName.CATIA, "cleanup", message)


class CatiaSession:
    """拥有一个隔离 CATIA 进程、Part 文档及当前线程的 COM 初始化。

    生命周期按严格的逆序释放：先关闭文档，再退出本会话创建的 CATIA
    应用，最后释放 Python COM 代理并调用 ``CoUninitialize``。清理失败不会
    遮蔽原始建模异常；无原始异常时则会显式报告 ``CatiaCleanupError``。
    """

    def __init__(
        self,
        *,
        application_factory: Callable[[str], Any] | None = None,
        com_initialize: Callable[[], None] | None = None,
        com_uninitialize: Callable[[], None] | None = None,
        collect_garbage: Callable[[], int] = gc.collect,
    ) -> None:
        # DispatchEx 请求独立的 COM 服务实例，使本工具可以安全拥有并退出它，
        # 避免误关用户已打开的 CATIA，同时保证批处理失败后不会留下隐藏进程。
        self._application_factory = (
            application_factory or _dispatch_isolated_application
        )
        self._com_initialize = com_initialize or _initialize_com
        self._com_uninitialize = com_uninitialize or _uninitialize_com
        self._collect_garbage = collect_garbage
        self._com_initialized = False
        self._closed = False
        self.application = None
        self.part_document = None
        self.part = None

    def __enter__(self) -> "CatiaSession":
        try:
            # 1. 当前线程进入 COM apartment；只有成功后才需要配对反初始化。
            self._com_initialize()
            self._com_initialized = True

            # 2. 本会话独占一个隐藏 CATIA 实例和一个 Part 文档。
            self.application = self._application_factory("CATIA.Application")
            self.application.Visible = False
            self.part_document = self.application.Documents.Add("Part")
            self.part = self.part_document.Part
            print("[INFO] Started isolated CATIA Automation session.")
            print("[INFO] Blank part created successfully.")
            return self
        except BaseException as error:
            # __enter__ 抛出时 Python 不会自动调用 __exit__，必须在这里回滚
            # 已完成的部分初始化，尤其是 DispatchEx 成功但 Add 失败的情况。
            self._cleanup(primary_error=error)
            raise

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self._cleanup(primary_error=exc_value)
        return False

    def _cleanup(self, *, primary_error: BaseException | None) -> None:
        if self._closed:
            return
        self._closed = True
        cleanup_errors: list[BaseException] = []

        # 1. 先断开 Part 代理，再关闭文档。即便关闭失败，也继续退出应用。
        self.part = None
        document = self.part_document
        self.part_document = None
        if document is not None:
            try:
                document.Close()
            except BaseException as error:
                cleanup_errors.append(error)
            finally:
                document = None

        # 2. 只退出由 DispatchEx 创建、归当前会话所有的 CATIA 实例。
        application = self.application
        self.application = None
        if application is not None:
            try:
                application.Quit()
            except BaseException as error:
                cleanup_errors.append(error)
            finally:
                application = None

        # 3. 强制回收残留的动态 COM 代理，再平衡当前线程的 COM 初始化。
        try:
            self._collect_garbage()
        except BaseException as error:
            cleanup_errors.append(error)

        if self._com_initialized:
            self._com_initialized = False
            try:
                self._com_uninitialize()
            except BaseException as error:
                cleanup_errors.append(error)

        if not cleanup_errors:
            return

        details = "; ".join(str(error) for error in cleanup_errors)
        message = f"CATIA cleanup failed: {details}"
        if primary_error is not None:
            primary_error.add_note(message)
            print(f"[WARNING] {message}")
            return
        raise CatiaCleanupError(message) from cleanup_errors[0]


def _load_pythoncom():
    """在实际启动后端时加载 pywin32，并把缺失依赖转换为能力错误。"""
    try:
        import pythoncom
    except ImportError as error:
        raise CatiaBackendUnavailableError(
            "CATIA backend is unavailable: pywin32 is not installed for "
            "this Python environment."
        ) from error
    return pythoncom


def _initialize_com() -> None:
    """初始化当前建模线程的 COM apartment。"""
    _load_pythoncom().CoInitialize()


def _uninitialize_com() -> None:
    """反初始化由当前会话建立的 COM apartment。"""
    _load_pythoncom().CoUninitialize()


def _dispatch_isolated_application(program_id: str):
    """通过 DispatchEx 创建归当前任务独占的 CATIA 应用实例。"""
    try:
        import win32com.client
    except ImportError as error:
        raise CatiaBackendUnavailableError(
            "CATIA backend is unavailable: pywin32 is not installed for "
            "this Python environment."
        ) from error
    return win32com.client.DispatchEx(program_id)
