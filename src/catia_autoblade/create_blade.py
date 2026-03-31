import os
import sys
import csv
import math
import win32com.client
import pythoncom

# 修复 CATIA COM 接口的枚举类型（部分版本需手动定义）
CATPart = "Part"
CATHybridShapePointCoord = 0  # 示例，实际以 CATIA API 为准
CATConstraintMode = 1

def create_part():
    try:
        # 连接/启动 CATIA
        pythoncom.CoInitialize()  # 初始化 COM
        caa = win32com.client.Dispatch("CATIA.Application")
        caa.Visible = False
        print(f"[INFO] Start CAA Automation via COM")

        # 创建 Part 文档
        documents = caa.Documents
        part_document = documents.Add(CATPart)
        part = part_document.Part
        print("[INFO] Blank part created successfully.")

        return caa, part_document, part
    except Exception as e:
        raise Exception(f"[ERROR] Error creating part: {e}") from e

def read_airfoil_csv(csv_path: str):
    # 保留原逻辑，无 CATIA 依赖
    try:
        points = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                x = float(row['x'])
                y = -float(row['y']) + 0.25
                z = float(row['z'])
                points.append((x, y, z))
        print(f"[INFO] Read {len(points)} points from CSV file.")
        return points
    except Exception as e:
        raise Exception(f"[ERROR] Error reading CSV file: {e}") from e

def create_airfoil(part, points: list):
    try:
        # COM 接口：获取 HybridBodies 和 HybridShapeFactory
        hybrid_bodies = part.HybridBodies
        gs_airfoil = hybrid_bodies.Add()
        gs_airfoil.Name = "airfoil"
        hybrid_shape_factory = part.HybridShapeFactory

        hybrid_shapes = []
        for i, (x, y, z) in enumerate(points):
            # COM 原生方法：创建点
            point = hybrid_shape_factory.AddNewPointCoord(x, y, z)
            gs_airfoil.AppendHybridShape(point)
            part.Update()  # COM 接口需手动更新
            hybrid_shapes.append(point)

        # 创建样条曲线
        spline = hybrid_shape_factory.AddNewSpline()
        for point in hybrid_shapes:
            reference = part.CreateReferenceFromObject(point)
            spline.AddPoint(reference)
        gs_airfoil.AppendHybridShape(spline)
        part.Update()
        print(f"[INFO] Airfoil spline created with {len(hybrid_shapes)} points.")

        first_point = points[0]
        last_point = points[-1]
        le_coord = (0.0, 0.25, 0.0)

        if first_point != last_point:
            is_sharp = False
            # 创建首尾点
            start_point = hybrid_shape_factory.AddNewPointCoord(
                first_point[0], first_point[1], first_point[2]
            )
            end_point = hybrid_shape_factory.AddNewPointCoord(
                last_point[0], last_point[1], last_point[2]
            )
            gs_airfoil.AppendHybridShape(start_point)
            gs_airfoil.AppendHybridShape(end_point)
            part.Update()

            # 创建连线
            start_point_ref = part.CreateReferenceFromObject(start_point)
            end_point_ref = part.CreateReferenceFromObject(end_point)
            line = hybrid_shape_factory.AddNewLinePtPt(start_point_ref, end_point_ref)
            gs_airfoil.AppendHybridShape(line)
            part.Update()
            print(f"[INFO] Line created to connect first and last points of airfoil cloud.")

            # 合并样条和直线
            spline_ref = part.CreateReferenceFromObject(spline)
            line_ref = part.CreateReferenceFromObject(line)
            join_feature = hybrid_shape_factory.AddNewJoin(spline_ref, line_ref)
            gs_airfoil.AppendHybridShape(join_feature)
            part.Update()
            print(f"[INFO] Spline and line joined successfully.")
            te_coord = (first_point, last_point)
            return gs_airfoil, join_feature, is_sharp, (le_coord, te_coord)
        else:
            is_sharp = True
            te_coord = (first_point,)
            return gs_airfoil, spline, is_sharp, (le_coord, te_coord)
    except Exception as e:
        raise Exception(f"[ERROR] Error creating airfoil cloud: {e}") from e

def read_section_parameters(csv_path: str):
    # 保留原逻辑，无 CATIA 依赖
    try:
        sections = []
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            header = next(reader)
            print(f"[INFO] CSV headers: {header}")
            for row in reader:
                section = {
                    'idx': int(row[0]),
                    'scale': float(row[1]),
                    'translate_x': float(row[2]),
                    'translate_y': float(row[3]),
                    'translate_z': float(row[4]),
                    'rotation': float(row[5])
                }
                sections.append(section)
        print(f"[INFO] Read {len(sections)} section parameters from CSV file.")
        return sections
    except Exception as e:
        raise Exception(f"[ERROR] Error reading section parameters: {e}") from e

def transform_point(px, py, pz, rotation_deg, scale, tx, ty, tz):
    # 保留原逻辑，无 CATIA 依赖
    angle_rad = math.radians(rotation_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    x_rotated = px
    y_rotated = py * cos_a - pz * sin_a
    z_rotated = py * sin_a + pz * cos_a
    new_x = x_rotated * scale + tx
    new_y = y_rotated * scale + ty
    new_z = z_rotated * scale + tz
    return (new_x, new_y, new_z)

def transform_airfoil_section(part, airfoil_ref, x_axis_ref, origin_ref, section):
    try:
        hsf = part.HybridShapeFactory
        # 旋转
        rotated = hsf.AddNewRotate(airfoil_ref, x_axis_ref, section['rotation'])
        part.Update()

        # 缩放
        rotated_ref = part.CreateReferenceFromObject(rotated)
        scaled = hsf.AddNewHybridScaling(rotated_ref, origin_ref, section['scale'])
        part.Update()

        # 平移
        scaled_ref = part.CreateReferenceFromObject(scaled)
        translate_dir = hsf.AddNewDirectionByCoord(
            section['translate_x'],
            section['translate_y'],
            section['translate_z']
        )
        translate_distance = math.sqrt(
            section['translate_x']**2 +
            section['translate_y']**2 +
            section['translate_z']**2
        )
        translated = hsf.AddNewTranslate(scaled_ref, translate_dir, translate_distance)
        part.Update()

        return translated
    except Exception as e:
        raise Exception(f"[ERROR] Error transforming section {section['idx']}: {e}") from e

def create_section_le_te_points(part, gs_blade, le_te_coords, section, le_points, te_upper_points, te_lower_points):
    try:
        hsf = part.HybridShapeFactory
        le_coord = le_te_coords[0]
        te_coord = le_te_coords[1]

        # 变换前缘点
        le_x, le_y, le_z = transform_point(
            le_coord[0], le_coord[1], le_coord[2],
            section['rotation'], section['scale'],
            section['translate_x'], section['translate_y'], section['translate_z']
        )
        le_final = hsf.AddNewPointCoord(le_x, le_y, le_z)
        gs_blade.AppendHybridShape(le_final)
        part.Update()
        le_points.append(le_final)

        # 变换后缘点
        if len(te_coord) == 2:
            te_upper_coord, te_lower_coord = te_coord
            # 上后缘点
            te_u_x, te_u_y, te_u_z = transform_point(
                te_upper_coord[0], te_upper_coord[1], te_upper_coord[2],
                section['rotation'], section['scale'],
                section['translate_x'], section['translate_y'], section['translate_z']
            )
            te_upper_final = hsf.AddNewPointCoord(te_u_x, te_u_y, te_u_z)
            gs_blade.AppendHybridShape(te_upper_final)
            part.Update()
            te_upper_points.append(te_upper_final)

            # 下后缘点
            te_l_x, te_l_y, te_l_z = transform_point(
                te_lower_coord[0], te_lower_coord[1], te_lower_coord[2],
                section['rotation'], section['scale'],
                section['translate_x'], section['translate_y'], section['translate_z']
            )
            te_lower_final = hsf.AddNewPointCoord(te_l_x, te_l_y, te_l_z)
            gs_blade.AppendHybridShape(te_lower_final)
            part.Update()
            te_lower_points.append(te_lower_final)
        else:
            te_single_coord = te_coord[0]
            te_x, te_y, te_z = transform_point(
                te_single_coord[0], te_single_coord[1], te_single_coord[2],
                section['rotation'], section['scale'],
                section['translate_x'], section['translate_y'], section['translate_z']
            )
            te_final = hsf.AddNewPointCoord(te_x, te_y, te_z)
            gs_blade.AppendHybridShape(te_final)
            part.Update()
            te_upper_points.append(te_final)
            te_lower_points.append(te_final)
    except Exception as e:
        raise Exception(f"[ERROR] Error creating LE/TE points for section {section['idx']}: {e}") from e

def create_blade_geometry(part, airfoil, le_te_coords, is_sharp, csv_path: str):
    try:
        hybrid_bodies = part.HybridBodies
        gs_blade = hybrid_bodies.Add()
        gs_blade.Name = "blade_geometry"

        hsf = part.HybridShapeFactory
        airfoil_ref = part.CreateReferenceFromObject(airfoil)
        section_params = read_section_parameters(csv_path)

        # 创建原点和X轴
        origin_point = hsf.AddNewPointCoord(0, 0, 0)
        gs_blade.AppendHybridShape(origin_point)
        part.Update()
        origin_ref = part.CreateReferenceFromObject(origin_point)

        x_dir = hsf.AddNewDirectionByCoord(1, 0, 0)
        x_axis = hsf.AddNewLinePtDir(origin_ref, x_dir, 0, 1000.0, True)
        gs_blade.AppendHybridShape(x_axis)
        part.Update()
        x_axis_ref = part.CreateReferenceFromObject(x_axis)

        le_points = []
        te_upper_points = []
        te_lower_points = []
        section_splines = []

        for section in section_params:
            # 变换翼型截面
            translated = transform_airfoil_section(
                part, airfoil_ref, x_axis_ref, origin_ref, section
            )
            gs_blade.AppendHybridShape(translated)
            part.Update()
            section_splines.append(translated)

            # 创建前缘/后缘点
            create_section_le_te_points(
                part, gs_blade, le_te_coords, section, le_points, te_upper_points, te_lower_points
            )

            print(f"[INFO] Section {section['idx']}: rotate={section['rotation']}deg, "
                  f"scale={section['scale']}, translate=({section['translate_x']}, "
                  f"{section['translate_y']}, {section['translate_z']})")

        # 创建前缘样条
        le_spline = hsf.AddNewSpline()
        for pt in le_points:
            ref = part.CreateReferenceFromObject(pt)
            le_spline.AddPoint(ref)
        gs_blade.AppendHybridShape(le_spline)
        part.Update()

        # 创建后缘上侧样条
        te_upper_spline = hsf.AddNewSpline()
        for pt in te_upper_points:
            ref = part.CreateReferenceFromObject(pt)
            te_upper_spline.AddPoint(ref)
        gs_blade.AppendHybridShape(te_upper_spline)
        part.Update()

        # 创建后缘下侧样条
        if is_sharp:
            te_lower_spline = te_upper_spline
        else:
            te_lower_spline = hsf.AddNewSpline()
            for pt in te_lower_points:
                ref = part.CreateReferenceFromObject(pt)
                te_lower_spline.AddPoint(ref)
            gs_blade.AppendHybridShape(te_lower_spline)
            part.Update()

        print("[INFO] Blade geometry created successfully.")
        return gs_blade, section_splines, le_spline, te_upper_spline, te_lower_spline, le_points

    except Exception as e:
        raise Exception(f"[ERROR] Error creating blade geometry: {e}") from e

def create_blade_surface(part, section_splines: list, le_spline, te_upper_spline, te_lower_spline, le_points, is_sharp):
    try:
        hybrid_bodies = part.HybridBodies
        gs_blade_surface = hybrid_bodies.Add()
        gs_blade_surface.Name = "blade_surface"

        hsf = part.HybridShapeFactory

        # 收集截面参考
        section_refs = []
        for spline in section_splines:
            ref = part.CreateReferenceFromObject(spline)
            section_refs.append(ref)

        # 收集前缘点参考
        le_point_refs = []
        for le_pt in le_points:
            le_pt_ref = part.CreateReferenceFromObject(le_pt)
            le_point_refs.append(le_pt_ref)

        # 创建扫掠曲面（Loft）
        le_ref = part.CreateReferenceFromObject(le_spline)
        te_upper_ref = part.CreateReferenceFromObject(te_upper_spline)
        blade_surface = hsf.AddNewLoft()
        
        for i, ref in enumerate(section_refs):
            le_pt_ref = le_point_refs[i]
            blade_surface.AddSectionToLoft(ref, 1, le_pt_ref)
        
        blade_surface.AddGuide(le_ref)
        blade_surface.AddGuide(te_upper_ref)
        if not is_sharp:
            te_lower_ref = part.CreateReferenceFromObject(te_lower_spline)
            blade_surface.AddGuide(te_lower_ref)
        
        gs_blade_surface.AppendHybridShape(blade_surface)
        part.Update()
        print("[INFO] Blade surface created successfully.")
        return gs_blade_surface, blade_surface

    except Exception as e:
        raise Exception(f"[ERROR] Error creating blade surface: {e}") from e

def create_blade_solid(part, surface):
    try:
        shape_factory = part.ShapeFactory
        bodies = part.Bodies
        new_body = bodies.Add()
        new_body.Name = "blade_solid"
        part.InWorkObject = new_body

        # 闭合曲面生成实体
        surface_ref = part.CreateReferenceFromObject(surface)
        blade_solid = shape_factory.AddNewCloseSurface(surface_ref)
        part.Update()
        print("[INFO] Blade solid created successfully.")
        return blade_solid

    except Exception as e:
        raise Exception(f"[ERROR] Error creating blade solid: {e}") from e

def save_part(part_document, output_dir, output_name="blade_part"):
    try:
        os.makedirs(output_dir, exist_ok=True)
        output_absdir = os.path.abspath(output_dir) # 必须使用绝对路径
        # 保存CATPart文件
        catpart_path = os.path.join(output_absdir, f"{output_name}.CATPart")
        if os.path.exists(catpart_path):
            os.remove(catpart_path)
        part_document.SaveAs(catpart_path)
        print(f"[INFO] Part saved to: {catpart_path}")
        # 导出STP文件
        stp_path = os.path.join(output_absdir, f"{output_name}.stp")
        if os.path.exists(stp_path):
            os.remove(stp_path)
        part_document.ExportData(stp_path, "stp")
        print(f"[INFO] Part exported to: {stp_path}")
    except Exception as e:
        raise Exception(f"[ERROR] Error saving part: {e}") from e

def hide_object(selection, obj):
    try:
        selection.Add(obj)
        selection.VisProperties.SetShow(1)
        selection.Clear()
    except Exception:
        pass

def hide_all_except_blade_solid(part_document, gs_airfoil, gs_blade_geometry, gs_blade_surface):
    try:
        selection = part_document.Selection
        hide_object(selection, gs_airfoil)
        hide_object(selection, gs_blade_geometry)
        hide_object(selection, gs_blade_surface)
        print("[INFO] Hidden gs_airfoil, gs_blade_geometry, gs_blade_surface.")
    except Exception as e:
        print(f"[WARNING] Error hiding objects: {e}")

def create_single_blade(airfoil_filename, section_params_filename, output_dir="output", output_name="blade"):
    caa, part_document, part = create_part()

    airfoil_path = os.path.join("input", "airfoils", airfoil_filename)
    points = read_airfoil_csv(airfoil_path)
    gs_airfoil, airfoil, is_sharp, le_te_coords = create_airfoil(part, points)

    section_params_path = os.path.join("input", "section_params", section_params_filename)
    gs_blade_geometry, section_splines, le_spline, te_upper_spline, te_lower_spline, le_points = create_blade_geometry(
        part, airfoil, le_te_coords, is_sharp, section_params_path
    )

    gs_blade_surface, blade_surface = create_blade_surface(
        part, section_splines, le_spline, te_upper_spline, te_lower_spline, le_points, is_sharp
    )

    blade_solid = create_blade_solid(part, blade_surface)
    hide_all_except_blade_solid(part_document, gs_airfoil, gs_blade_geometry, gs_blade_surface)

    try:
        part.Update()
    except Exception as e:
        print(f"[WARNING] Part update failed: {e}")

    save_part(part_document, output_dir, output_name)

    caa.Quit()
    pythoncom.CoUninitialize()

    return output_name, output_dir

if __name__ == "__main__":
    create_single_blade("sc1095.csv", "section_params-1.csv")