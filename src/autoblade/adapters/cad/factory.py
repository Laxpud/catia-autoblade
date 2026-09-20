"""内部显式后端工厂；没有 entry-point、动态模块名或自动探测回退。"""

from ...core.backend import BackendName, BackendError, CadBackend
from ...core.jobs import BladeBuildJob


class CatiaBackend:
    """把已有 CATIA API 接到统一任务接口，保持每任务独占 COM 生命周期。"""

    def build(self, job: BladeBuildJob) -> None:
        """把已解析输入传给原 Builder；不重新解析或组合输入。"""
        from ...core.create_blade import create_single_blade

        try:
            create_single_blade(
                job.airfoil_filename,
                job.blade_sections_filename,
                job.output_dir,
                job.output_name,
                airfoil_dir=job.airfoil_dir,
                blade_sections_dir=job.blade_sections_dir,
                keep_failed_part=job.keep_failed_part,
                input_plan=job.input_plan,
            )
        except BackendError:
            raise
        except Exception as error:
            mapped = BackendError(BackendName.CATIA, "geometry", str(error))
            for note in getattr(error, "__notes__", []):
                mapped.add_note(note)
            raise mapped from error



def get_backend(name: BackendName) -> CadBackend:
    """仅装载显式选择的 Adapter；导入工厂本身不会装载 CAD 运行时。"""
    selected = BackendName(name)
    if selected == BackendName.CATIA:
        return CatiaBackend()
    from .freecad.adapter import FreeCADBackend

    return FreeCADBackend()
