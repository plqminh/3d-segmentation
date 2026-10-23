"""
ModelSplitter - 3D Print Bed Visualizer & Auto-Arranger
Manages non-renderable print volume wireframe visualization and
2D collision-aware part shelf-packing onto the build plate at Z = 0.
"""

import bpy
from mathutils import Vector
from ..utils.math_utils import mm_to_scene_units, get_world_bounds
from ..utils.mesh_utils import get_or_create_collection


PRINT_BED_OBJ_NAME = "MS_Print_Bed_Plate"
PRINT_BED_COL_NAME = "ModelSplitter_Helpers"


def update_print_bed_visualizer(context):
    """Creates or updates the 3D wireframe build plate volume in the viewport."""
    settings = getattr(context.scene, "model_splitter", None)
    if not settings:
        return

    bed_props = settings.print_bed
    if not bed_props.show_bed:
        # Hide or remove
        obj = bpy.data.objects.get(PRINT_BED_OBJ_NAME)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
        return

    # Dimensions in scene units
    w = mm_to_scene_units(context, bed_props.bed_x_mm)
    d = mm_to_scene_units(context, bed_props.bed_y_mm)
    h = mm_to_scene_units(context, bed_props.bed_z_mm)

    hw = w * 0.5
    hd = d * 0.5

    # Check if object already exists
    obj = bpy.data.objects.get(PRINT_BED_OBJ_NAME)
    mesh = obj.data if obj else bpy.data.meshes.new(f"{PRINT_BED_OBJ_NAME}_Mesh")

    # Build wireframe box with bottom plate grid corners
    coords = [
        Vector((-hw, -hd, 0.0)),
        Vector((hw, -hd, 0.0)),
        Vector((hw, hd, 0.0)),
        Vector((-hw, hd, 0.0)),
        Vector((-hw, -hd, h)),
        Vector((hw, -hd, h)),
        Vector((hw, hd, h)),
        Vector((-hw, hd, h)),
    ]

    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),  # Bottom perimeter
        (4, 5), (5, 6), (6, 7), (7, 4),  # Top perimeter
        (0, 4), (1, 5), (2, 6), (3, 7),  # Vertical pillars
        (0, 2), (1, 3),                  # Ground diagonal cross
    ]

    mesh.clear_geometry()
    mesh.from_pydata(coords, edges, [])
    mesh.update()

    if not obj:
        obj = bpy.data.objects.new(PRINT_BED_OBJ_NAME, mesh)
        helper_col = get_or_create_collection(context, name=PRINT_BED_COL_NAME)
        helper_col.objects.link(obj)

    obj.display_type = 'WIRE'
    obj.hide_render = True
    obj.show_in_front = True
    obj.location = Vector((0.0, 0.0, 0.0))


def pack_parts_on_bed(context, objects, margin_mm=10.0):
    """
    Arranges the given list of mesh objects onto the ground plane (Z = 0)
    using 2D shelf-packing with margin, centered at world origin.
    Returns (packed_count, out_of_bounds_count).
    """
    settings = context.scene.model_splitter
    bed_props = settings.print_bed
    bed_w = mm_to_scene_units(context, bed_props.bed_x_mm)
    bed_d = mm_to_scene_units(context, bed_props.bed_y_mm)
    margin = mm_to_scene_units(context, margin_mm)

    valid_objs = [o for o in objects if o.type == 'MESH' and o.name != PRINT_BED_OBJ_NAME]
    if not valid_objs:
        return 0, 0

    # First, make sure origins are centered on geometry bounds and drops each to Z = 0
    obj_data = []
    for obj in valid_objs:
        # Move origin to bottom center of bounding box
        min_c, max_c, center, dims = get_world_bounds(obj)
        # Shift object so its lowest vertex is at Z = 0
        obj.location.z -= min_c.z
        context.view_layer.update()
        min_c, max_c, center, dims = get_world_bounds(obj)
        obj_data.append({
            'obj': obj,
            'w': dims.x,
            'd': dims.y,
            'h': dims.z,
        })

    # Sort objects by depth/height descending for tidy row shelf packing
    obj_data.sort(key=lambda item: max(item['w'], item['d']), reverse=True)

    # Shelf packing algorithm
    max_row_width = bed_w - (margin * 2.0)
    current_x = 0.0
    current_y = 0.0
    current_row_height = 0.0

    placements = []
    total_min_x = float('inf')
    total_max_x = float('-inf')
    total_min_y = float('inf')
    total_max_y = float('-inf')

    for item in obj_data:
        pw = item['w']
        pd = item['d']

        if current_x + pw > max_row_width and current_x > 0.0:
            # Move to next shelf row
            current_x = 0.0
            current_y += current_row_height + margin
            current_row_height = 0.0

        target_x = current_x + (pw * 0.5)
        target_y = current_y + (pd * 0.5)

        placements.append((item['obj'], target_x, target_y))

        current_row_height = max(current_row_height, pd)
        current_x += pw + margin

        total_min_x = min(total_min_x, target_x - pw * 0.5)
        total_max_x = max(total_max_x, target_x + pw * 0.5)
        total_min_y = min(total_min_y, target_y - pd * 0.5)
        total_max_y = max(total_max_y, target_y + pd * 0.5)

    # Compute offset to center the packed layout onto (0, 0) of the print bed
    center_shift_x = -((total_min_x + total_max_x) * 0.5)
    center_shift_y = -((total_min_y + total_max_y) * 0.5)

    out_of_bounds = 0
    half_bed_w = bed_w * 0.5
    half_bed_d = bed_d * 0.5

    for obj, px, py in placements:
        final_x = px + center_shift_x
        final_y = py + center_shift_y

        min_c, max_c, c, dims = get_world_bounds(obj)
        delta_x = final_x - c.x
        delta_y = final_y - c.y

        obj.location.x += delta_x
        obj.location.y += delta_y
        context.view_layer.update()

        # Re-check if within bed limits
        new_min_c, new_max_c, _, _ = get_world_bounds(obj)
        if (abs(new_min_c.x) > half_bed_w or abs(new_max_c.x) > half_bed_w or
            abs(new_min_c.y) > half_bed_d or abs(new_max_c.y) > half_bed_d):
            out_of_bounds += 1

    return len(valid_objs), out_of_bounds
