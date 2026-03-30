import os
import sys
import csv
import math
from pycatia import catia
from pycatia.mec_mod_interfaces.part_document import PartDocument
from pycatia.mec_mod_interfaces.part import Part
from pycatia.part_interfaces.close_surface import CloseSurface

def create_part():
    try:
        caa = catia()
        print(f"[INFO] Start CAA Automation")
        caa.visible = False

        documents = caa.documents
        part_document: PartDocument = documents.add("Part")
        part: Part = part_document.part
        print("[INFO] Blank part created successfully.")

        return caa, part_document, part
    except Exception as e:
        raise Exception(f"[ERROR] Error creating part: {e}") from e

def read_airfoil_csv(csv_path: str):
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

def create_airfoil(part: Part, points: list):
    try:
        hybrid_bodies = part.hybrid_bodies
        gs_airfoil = hybrid_bodies.add()
        gs_airfoil.name = "airfoil"

        hybrid_shape_factory = part.hybrid_shape_factory

        hybrid_shapes = []
        for i, (x, y, z) in enumerate(points):
            point = hybrid_shape_factory.add_new_point_coord(x, y, z)
            gs_airfoil.append_hybrid_shape(point)
            hybrid_shapes.append(point)

        spline = hybrid_shape_factory.add_new_spline()
        for point in hybrid_shapes:
            reference = part.create_reference_from_object(point)
            spline.add_point(reference)
        gs_airfoil.append_hybrid_shape(spline)
        print(f"[INFO] Airfoil spline created with {len(hybrid_shapes)} points.")

        first_point = points[0]
        last_point = points[-1]
        le_coord = (0.0, 0.25, 0.0)

        if first_point != last_point:
            is_sharp = False
            start_point = hybrid_shape_factory.add_new_point_coord(
                first_point[0], first_point[1], first_point[2]
            )
            end_point = hybrid_shape_factory.add_new_point_coord(
                last_point[0], last_point[1], last_point[2]
            )
            gs_airfoil.append_hybrid_shape(start_point)
            gs_airfoil.append_hybrid_shape(end_point)
            start_point_ref = part.create_reference_from_object(start_point)
            end_point_ref = part.create_reference_from_object(end_point)
            line = hybrid_shape_factory.add_new_line_pt_pt(start_point_ref, end_point_ref)
            gs_airfoil.append_hybrid_shape(line)
            print(f"[INFO] Line created to connect first and last points of airfoil cloud.")

            spline_ref = part.create_reference_from_object(spline)
            line_ref = part.create_reference_from_object(line)
            join_feature = hybrid_shape_factory.add_new_join(spline_ref, line_ref)
            gs_airfoil.append_hybrid_shape(join_feature)
            print(f"[INFO] Spline and line joined successfully.")
            te_coord = (first_point, last_point)
            return gs_airfoil, join_feature, is_sharp, (le_coord, te_coord)
        else:
            is_sharp = True
            te_coord = (first_point,)
            return gs_airfoil, spline, is_sharp, (le_coord, te_coord)
    except Exception as e:
        raise Exception(f"[ERROR] Error creating airfoil cloud: {e}") from e

def read_section_parameters():
    try:
        csv_path = os.path.join(os.path.dirname(__file__), "input", "section_params.csv")
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

def transform_airfoil_section(part: Part, airfoil_ref, x_axis_ref, origin_ref, section):
    try:
        hsf = part.hybrid_shape_factory
        rotated = hsf.add_new_rotate(airfoil_ref, x_axis_ref, section['rotation'])

        rotated_ref = part.create_reference_from_object(rotated)
        scaled = hsf.add_new_hybrid_scaling(rotated_ref, origin_ref, section['scale'])

        scaled_ref = part.create_reference_from_object(scaled)
        translate_dir = hsf.add_new_direction_by_coord(
            section['translate_x'],
            section['translate_y'],
            section['translate_z']
        )
        translate_distance = (
            section['translate_x']**2 +
            section['translate_y']**2 +
            section['translate_z']**2
        ) ** 0.5
        translated = hsf.add_new_translate(scaled_ref, translate_dir, translate_distance)

        return translated
    except Exception as e:
        raise Exception(f"[ERROR] Error transforming section {section['idx']}: {e}") from e

def create_section_le_te_points(part: Part, gs_blade, le_te_coords, section, le_points, te_upper_points, te_lower_points):
    try:
        hsf = part.hybrid_shape_factory
        le_coord = le_te_coords[0]
        te_coord = le_te_coords[1]

        le_x, le_y, le_z = transform_point(
            le_coord[0], le_coord[1], le_coord[2],
            section['rotation'], section['scale'],
            section['translate_x'], section['translate_y'], section['translate_z']
        )
        le_final = hsf.add_new_point_coord(le_x, le_y, le_z)
        gs_blade.append_hybrid_shape(le_final)
        le_points.append(le_final)

        if len(te_coord) == 2:
            te_upper_coord, te_lower_coord = te_coord
            te_u_x, te_u_y, te_u_z = transform_point(
                te_upper_coord[0], te_upper_coord[1], te_upper_coord[2],
                section['rotation'], section['scale'],
                section['translate_x'], section['translate_y'], section['translate_z']
            )
            te_upper_final = hsf.add_new_point_coord(te_u_x, te_u_y, te_u_z)
            gs_blade.append_hybrid_shape(te_upper_final)
            te_upper_points.append(te_upper_final)

            te_l_x, te_l_y, te_l_z = transform_point(
                te_lower_coord[0], te_lower_coord[1], te_lower_coord[2],
                section['rotation'], section['scale'],
                section['translate_x'], section['translate_y'], section['translate_z']
            )
            te_lower_final = hsf.add_new_point_coord(te_l_x, te_l_y, te_l_z)
            gs_blade.append_hybrid_shape(te_lower_final)
            te_lower_points.append(te_lower_final)
        else:
            te_single_coord = te_coord[0]
            te_x, te_y, te_z = transform_point(
                te_single_coord[0], te_single_coord[1], te_single_coord[2],
                section['rotation'], section['scale'],
                section['translate_x'], section['translate_y'], section['translate_z']
            )
            te_final = hsf.add_new_point_coord(te_x, te_y, te_z)
            gs_blade.append_hybrid_shape(te_final)
            te_upper_points.append(te_final)
            te_lower_points.append(te_final)
    except Exception as e:
        raise Exception(f"[ERROR] Error creating LE/TE points for section {section['idx']}: {e}") from e

def create_blade_geometry(part: Part, airfoil, le_te_coords, is_sharp):
    try:
        hybrid_bodies = part.hybrid_bodies
        gs_blade = hybrid_bodies.add()
        gs_blade.name = "blade_geometry"

        hsf = part.hybrid_shape_factory
        airfoil_ref = part.create_reference_from_object(airfoil)
        section_params = read_section_parameters()

        origin_point = hsf.add_new_point_coord(0, 0, 0)
        gs_blade.append_hybrid_shape(origin_point)
        origin_ref = part.create_reference_from_object(origin_point)

        x_dir = hsf.add_new_direction_by_coord(1, 0, 0)
        x_axis = hsf.add_new_line_pt_dir(origin_ref, x_dir, 0, 1000.0, True)
        x_axis_ref = part.create_reference_from_object(x_axis)

        le_points = []
        te_upper_points = []
        te_lower_points = []
        section_splines = []

        for section in section_params:

            translated = transform_airfoil_section(
                part, airfoil_ref, x_axis_ref, origin_ref, section
            )
            gs_blade.append_hybrid_shape(translated)
            section_splines.append(translated)

            create_section_le_te_points(
                part, gs_blade, le_te_coords, section, le_points, te_upper_points, te_lower_points
            )

            print(f"[INFO] Section {section['idx']}: rotate={section['rotation']}deg, "
                  f"scale={section['scale']}, translate=({section['translate_x']}, "
                  f"{section['translate_y']}, {section['translate_z']})")

        le_spline = hsf.add_new_spline()
        for pt in le_points:
            ref = part.create_reference_from_object(pt)
            le_spline.add_point(ref)
        gs_blade.append_hybrid_shape(le_spline)

        te_upper_spline = hsf.add_new_spline()
        for pt in te_upper_points:
            ref = part.create_reference_from_object(pt)
            te_upper_spline.add_point(ref)
        gs_blade.append_hybrid_shape(te_upper_spline)

        if is_sharp:
            te_lower_spline = te_upper_spline
        else:
            te_lower_spline = hsf.add_new_spline()
            for pt in te_lower_points:
                ref = part.create_reference_from_object(pt)
                te_lower_spline.add_point(ref)
            gs_blade.append_hybrid_shape(te_lower_spline)

        print("[INFO] Blade geometry created successfully.")
        return gs_blade, section_splines, le_spline, te_upper_spline, te_lower_spline, le_points

    except Exception as e:
        raise Exception(f"[ERROR] Error creating blade geometry: {e}") from e

def create_blade_surface(part: Part, section_splines: list, le_spline, te_upper_spline, te_lower_spline, le_points, is_sharp):
    try:
        hybrid_bodies = part.hybrid_bodies
        gs_blade_surface = hybrid_bodies.add()
        gs_blade_surface.name = "blade_surface"

        hsf = part.hybrid_shape_factory

        section_refs = []
        for spline in section_splines:
            ref = part.create_reference_from_object(spline)
            section_refs.append(ref)

        le_point_refs = []
        for le_pt in le_points:
            le_pt_ref = part.create_reference_from_object(le_pt)
            le_point_refs.append(le_pt_ref)

        le_ref = part.create_reference_from_object(le_spline)
        te_upper_ref = part.create_reference_from_object(te_upper_spline)

        blade_surface = hsf.add_new_loft()
        for i, ref in enumerate(section_refs):
            le_pt_ref = le_point_refs[i]
            blade_surface.add_section_to_loft(ref, 1, le_pt_ref)
        blade_surface.add_guide(le_ref)
        blade_surface.add_guide(te_upper_ref)
        if not is_sharp:
            te_lower_ref = part.create_reference_from_object(te_lower_spline)
            blade_surface.add_guide(te_lower_ref)
        gs_blade_surface.append_hybrid_shape(blade_surface)

        # 填充桨根和桨尖平面
        # blade_surface_ref = part.create_reference_from_object(blade_surface)

        # root_section_ref = section_refs[0]
        # root_fill = hsf.add_new_fill()
        # root_fill.add_bound(root_section_ref)
        # gs_blade_surface.append_hybrid_shape(root_fill)

        # tip_section_ref = section_refs[-1]
        # tip_fill = hsf.add_new_fill()
        # tip_fill.add_bound(tip_section_ref)
        # gs_blade_surface.append_hybrid_shape(tip_fill)

        # 接合
        # blade_surface_ref = part.create_reference_from_object(blade_surface)
        # root_fill_ref = part.create_reference_from_object(root_fill)
        # tip_fill_ref = part.create_reference_from_object(tip_fill)

        # join_surface = hsf.add_new_join(blade_surface_ref, root_fill_ref)
        # join_surface.add_element(tip_fill_ref)
        # join_surface.set_deviation(0.01)  # 合并距离
        # join_surface.set_connex(True)  # 检查连通性，避免缝合非连续曲面
        # join_surface.set_manifold(True)  # 检查流形，避免生成错误几何体
        # gs_blade_surface.append_hybrid_shape(join_surface)

        print("[INFO] Blade surface created successfully.")
        # return gs_blade_surface, join_surface
        return gs_blade_surface, blade_surface

    except Exception as e:
        raise Exception(f"[ERROR] Error creating blade surface: {e}") from e

def create_blade_solid(part: Part, surface):
    try:
        shape_factory = part.shape_factory
        bodies = part.bodies
        new_body = bodies.add()
        new_body.name = "blade_solid"
        part.in_work_object = new_body

        surface_ref = part.create_reference_from_object(surface)

        blade_solid: CloseSurface = shape_factory.add_new_close_surface(surface_ref)

        part.update()
        print("[INFO] Blade solid created successfully.")
        return blade_solid

    except Exception as e:
        raise Exception(f"[ERROR] Error creating blade solid: {e}") from e

def save_part(part_document: PartDocument):
    try:
        save_path = os.path.join(os.path.dirname(__file__), "blade_part.CATPart")
        part_document.save_as(save_path, overwrite=True)
        print(f"[INFO] Part saved successfully to: {save_path}")

        # stp_path = os.path.join(os.path.dirname(__file__), "blade_part.stp")
        # part_document.save_as(stp_path, overwrite=True)
        # print(f"[INFO] Part saved as STP successfully to: {stp_path}")
    except Exception as e:
        raise Exception(f"[ERROR] Error saving part: {e}") from e

if __name__ == "__main__":
    caa, part_document, part = create_part()

    airfoil_file = "airfoil_sc1095.csv"
    csv_path = os.path.join(os.path.dirname(__file__), "input", airfoil_file)
    points = read_airfoil_csv(csv_path)

    gs_airfoil, airfoil, is_sharp, le_te_coords = create_airfoil(part, points)

    gs_blade_geometry, section_splines, le_spline, te_upper_spline, te_lower_spline, le_points = create_blade_geometry(part, airfoil, le_te_coords, is_sharp)

    gs_blade_surface, blade_surface = create_blade_surface(part, section_splines, le_spline, te_upper_spline, te_lower_spline, le_points, is_sharp)

    # acdoc = caa.active_document
    # selection = acdoc.selection
    # selection.clear()
    # selection.add(gs_blade_surface)
    # try:
    #     selection.vis_properties.set_show(2)
    #     print("[INFO] Blade surface hidden successfully.")
    # except Exception as e:
    #     print(f"[ERROR] Failed to hide blade surface: {e}")
    # finally:
    #     selection.clear()

    blade_solid = create_blade_solid(part, blade_surface)

    try:
        part.update()
    except Exception as e:
        print(f"[WARNING] Part update failed. Please open the CATPart file manually, right-click the part in the specification tree and select 'Update' to see detailed error messages. Original error: {e}")

    save_part(part_document)

    caa.quit()
    print("[INFO] CAA closed.")
