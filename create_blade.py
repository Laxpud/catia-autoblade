import os
import sys
import csv
from pycatia import catia
from pycatia.mec_mod_interfaces.part_document import PartDocument
from pycatia.mec_mod_interfaces.part import Part

def create_part():
    try:
        caa = catia()
        caa.visible = False

        documents = caa.documents
        part_document: PartDocument = documents.add("Part")
        part: Part = part_document.part
        print("[INFO] Blank part created successfully.")

        return caa, part_document, part
    except Exception as e:
        print(f"[ERROR] Error creating part: {e}")
        sys.exit(1)

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
        print(f"[ERROR] Error reading CSV file: {e}")
        sys.exit(1)

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
        if first_point != last_point:
            line = hybrid_shape_factory.add_new_line_coord(
                first_point[0], first_point[1], first_point[2],
                last_point[0], last_point[1], last_point[2]
            )
            gs_airfoil.append_hybrid_shape(line)
            print(f"[INFO] Line created to connect first and last points of airfoil cloud.")

            spline_ref = part.create_reference_from_object(spline)
            line_ref = part.create_reference_from_object(line)
            assemble = hybrid_shape_factory.add_new_assemble(gs_airfoil, [spline_ref, line_ref])
            print(f"[INFO] Spline and line assembled successfully.")
            return gs_airfoil, assemble, True
        else:
            return gs_airfoil, spline, False
    except Exception as e:
        print(f"[ERROR] Error creating airfoil cloud: {e}")
        sys.exit(1)

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
        print(f"[ERROR] Error reading section parameters: {e}")
        sys.exit(1)

def create_blade_geometry(part: Part, airfoil):
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

        for section in section_params:
            rotated = hsf.add_new_rotate(airfoil_ref, x_axis_ref, section['rotation'])
            gs_blade.append_hybrid_shape(rotated)

            rotated_ref = part.create_reference_from_object(rotated)
            scaled = hsf.add_new_hybrid_scaling(rotated_ref, origin_ref, section['scale'])
            gs_blade.append_hybrid_shape(scaled)

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
            gs_blade.append_hybrid_shape(translated)

            print(f"[INFO] Section {section['idx']}: rotate={section['rotation']}deg, "
                  f"scale={section['scale']}, offset=({section['translate_x']}, "
                  f"{section['translate_y']}, {section['translate_z']})")

        print("[INFO] Blade geometry created successfully.")
        return gs_blade

    except Exception as e:
        print(f"[ERROR] Error creating blade geometry: {e}")
        sys.exit(1)


def save_part(part_document: PartDocument):
    try:
        save_path = os.path.join(os.path.dirname(__file__), "blade_part.CATPart")
        part_document.save_as(save_path, overwrite=True)
        print(f"[INFO] Part saved successfully to: {save_path}")
    except Exception as e:
        print(f"[ERROR] Error saving part: {e}")
        sys.exit(1)

if __name__ == "__main__":
    caa, part_document, part = create_part()

    airfoil_file = "airfoil_sc1095.csv"
    csv_path = os.path.join(os.path.dirname(__file__), "input", airfoil_file)
    points = read_airfoil_csv(csv_path)

    gs_airfoil, airfoil, is_sharp = create_airfoil(part, points)

    gs_blade = create_blade_geometry(part, airfoil)

    try:
        part.update()
    except Exception as e:
        print(f"[WARNING] Part update failed. Please open the CATPart file manually,")
        print(f"[WARNING] right-click the part in the specification tree and select 'Update'")
        print(f"[WARNING] to see detailed error messages.")

    save_part(part_document)

    caa.quit()