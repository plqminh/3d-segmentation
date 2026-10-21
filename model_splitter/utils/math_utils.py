"""
ModelSplitter - Math and Geometry Utilities
Handles bounding box calculations, vector transformations, and connector spatial distributions.
"""

import math
from mathutils import Vector, Matrix, Quaternion


def get_world_bounds(obj):
    """
    Computes axis-aligned bounding box of an object in world coordinates.
    Returns (min_corner, max_corner, center, dimensions).
    """
    matrix_world = obj.matrix_world
    corners = [matrix_world @ Vector(corner) for corner in obj.bound_box]
    
    min_x = min(c.x for c in corners)
    max_x = max(c.x for c in corners)
    min_y = min(c.y for c in corners)
    max_y = max(c.y for c in corners)
    min_z = min(c.z for c in corners)
    max_z = max(c.z for c in corners)
    
    min_corner = Vector((min_x, min_y, min_z))
    max_corner = Vector((max_x, max_y, max_z))
    center = (min_corner + max_corner) * 0.5
    dimensions = max_corner - min_corner
    
    return min_corner, max_corner, center, dimensions


def get_scene_scale_to_mm(context, ref_obj=None):
    """
    Determines multiplier to convert Blender scene units to millimeters for 3D printing.
    - If the user explicitly configured a custom Blender unit scale (e.g. 0.001 for mm), respects it.
    - In Blender's default scene (scale_length == 1.0), automatically adapts to the model's coordinate scale:
      * Millimeter-scale STL/OBJ models (max_dim >= 25 BU): 1 BU = 1 mm (scale_to_mm = 1.0)
      * Centimeter-scale models (8 <= max_dim < 25 BU):     1 BU = 10 mm (scale_to_mm = 10.0)
      * Standard Blender scale (max_dim < 8 BU, e.g. 2 BU): 2 BU = 100 mm print (scale_to_mm = 50.0)
    """
    import bpy
    unit_settings = context.scene.unit_settings
    if unit_settings.system == 'METRIC' and abs(unit_settings.scale_length - 1.0) > 1e-4:
        return unit_settings.scale_length * 1000.0

    if ref_obj is None:
        settings = getattr(context.scene, "model_splitter", None)
        if settings and getattr(settings.cut, "active_source_name", ""):
            ref_obj = bpy.data.objects.get(settings.cut.active_source_name)
        if ref_obj is None:
            ref_obj = getattr(context, "active_object", None)

    if ref_obj is not None and getattr(ref_obj, "type", "") == 'MESH':
        try:
            _, _, _, dims = get_world_bounds(ref_obj)
            max_dim = max(dims.x, dims.y, dims.z)
            if max_dim >= 25.0:
                return 1.0
            elif max_dim >= 8.0:
                return 10.0
        except Exception:
            pass

    return 50.0


def mm_to_scene_units(context, mm_value, ref_obj=None):
    """Converts a millimeter value to Blender internal scene units."""
    scale_to_mm = get_scene_scale_to_mm(context, ref_obj=ref_obj)
    if scale_to_mm <= 0:
        scale_to_mm = 50.0
    return mm_value / scale_to_mm


def scene_units_to_mm(context, scene_value, ref_obj=None):
    """Converts a Blender internal scene value to millimeters."""
    scale_to_mm = get_scene_scale_to_mm(context, ref_obj=ref_obj)
    return scene_value * scale_to_mm



def rotation_align_vector(source_vec, target_vec):
    """
    Returns a Matrix that rotates source_vec to align with target_vec.
    Default source is Z-axis (0, 0, 1).
    """
    source = source_vec.normalized()
    target = target_vec.normalized()
    
    dot = source.dot(target)
    
    if dot >= 0.999999:
        return Matrix.Identity(4)
    elif dot <= -0.999999:
        # 180 degree rotation around any orthogonal axis
        ortho = Vector((1, 0, 0)) if abs(source.x) < 0.9 else Vector((0, 1, 0))
        axis = source.cross(ortho).normalized()
        return Matrix.Rotation(math.pi, 4, axis)
    
    axis = source.cross(target).normalized()
    angle = math.acos(max(-1.0, min(1.0, dot)))
    return Matrix.Rotation(angle, 4, axis)


def distribute_connectors_2d(count, radius):
    """
    Generates (x, y) 2D local offsets for N connectors (1 to 5).
    Positions are symmetrically arranged within a given radius.
    """
    if count <= 0:
        return []
    if count == 1:
        return [Vector((0.0, 0.0, 0.0))]
    elif count == 2:
        return [
            Vector((-radius * 0.65, 0.0, 0.0)),
            Vector((radius * 0.65, 0.0, 0.0))
        ]
    elif count == 3:
        offsets = []
        for i in range(3):
            angle = i * (2.0 * math.pi / 3.0) + (math.pi / 2.0)
            offsets.append(Vector((math.cos(angle) * radius * 0.6, math.sin(angle) * radius * 0.6, 0.0)))
        return offsets
    elif count == 4:
        r = radius * 0.55
        return [
            Vector((-r, -r, 0.0)),
            Vector((r, -r, 0.0)),
            Vector((r, r, 0.0)),
            Vector((-r, r, 0.0)),
        ]
    elif count >= 5:
        # Center plus 4 corners
        r = radius * 0.65
        return [
            Vector((0.0, 0.0, 0.0)),
            Vector((-r, 0.0, 0.0)),
            Vector((r, 0.0, 0.0)),
            Vector((0.0, -r, 0.0)),
            Vector((0.0, r, 0.0)),
        ]
