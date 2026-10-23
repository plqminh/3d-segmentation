"""
Automated test suite for ModelSplitter's Drawing Cut Line System.
Tests:
- Screen-line cutter generation and projection
- Screen-curve cutter generation
- Surface-contour 3D cutter generation
- Exact boolean splitting along drawn cuts
- Pin & socket connector generation at drawn cut interfaces
- Swap pin target side
- Explode separation
"""

import sys
import os
import bpy
from mathutils import Vector, Matrix

# Ensure addon is in path
workspace_dir = r"e:\3D segmentation"
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

print("[TEST-DRAW] Registering model_splitter...")
import model_splitter
model_splitter.register()
print("[TEST-DRAW] Addon registered successfully!")

# Clean scene
bpy.ops.wm.read_factory_settings(use_empty=True)

# 1. Create a mock region and region_data (or 3D view context)
class MockRV3D:
    def __init__(self):
        # Camera looking down -Z axis from (0, 0, 5)
        self.view_rotation = Matrix.Identity(3).to_quaternion()
        self.view_distance = 5.0
        self.view_matrix = Matrix.Translation(Vector((0, 0, -5)))
        self.is_perspective = True

class MockRegion:
    def __init__(self):
        self.width = 1920
        self.height = 1080
        self.x = 0
        self.y = 0

mock_rv3d = MockRV3D()
mock_region = MockRegion()

# 2. Test Mesh Creation
print("[TEST-DRAW] Spawning test UV Sphere...")
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 0))
sphere = bpy.context.active_object
assert sphere is not None, "Sphere creation failed!"

# 3. Test Screen-Line Cutter Generation
print("[TEST-DRAW] Testing create_cutter_from_screen_line...")
from model_splitter.core.cutter_geometry import (
    create_cutter_from_screen_line,
    create_cutter_from_screen_curve,
    create_cutter_from_surface_points,
)

# Diagonal cut line across screen center
p1_2d = Vector((300, 400))
p2_2d = Vector((1600, 700))

cutter_line, plane_vis, p_center, p_normal, w_mat = create_cutter_from_screen_line(
    bpy.context,
    sphere,
    p1_2d,
    p2_2d,
    mock_region,
    mock_rv3d,
)

assert cutter_line is not None, "Line cutter object is None!"
print(f"[TEST-DRAW] Line cutter created: {cutter_line.name}, center: {p_center}, normal: {p_normal}")

# 4. Test Draft Mode with Drawn Line Cutter
print("[TEST-DRAW] Entering Draft Mode with drawn cutter...")
from model_splitter.core.draft_manager import enter_draft_mode, apply_draft_build, swap_pin_target

settings = bpy.context.scene.model_splitter
settings.cut.workflow_mode = 'DRAFT'
settings.connector.shape = 'CYLINDER'
settings.connector.count = 2
settings.connector.diameter_mm = 5.0
settings.connector.clearance_mm = 0.2

enter_draft_mode(bpy.context, sphere, cut_type='STRAIGHT', existing_cutter=cutter_line, custom_world_mat=w_mat)
assert settings.cut.is_in_draft, "Draft mode not active!"
print("[TEST-DRAW] In draft mode successfully with drawn cutter!")

# 5. Test Swap Pin Target
print("[TEST-DRAW] Testing Swap Pin Side...")
assert settings.connector.target_side == 'PART_A'
swap_pin_target(bpy.context)
assert settings.connector.target_side == 'PART_B'
print(f"[TEST-DRAW] Successfully swapped pin target to {settings.connector.target_side}!")

# 6. Test Explode Setting and Build
print("[TEST-DRAW] Testing Explode Separation and Build...")
settings.cut.explode_distance_mm = 15.0  # 15mm visual separation
parts = apply_draft_build(bpy.context)
assert len(parts) >= 2, f"Expected at least 2 split parts, got {len(parts)}"
print(f"[TEST-DRAW] Cut applied successfully! Generated {len(parts)} parts: {[p.name for p in parts]}")

# 7. Test Curved Screen Cut on Suzanne (Full Draft Mode + Alignment Verification)
print("[TEST-DRAW] Testing Curved Screen Cut on Suzanne with Draft Mode & Alignment Verification...")
bpy.ops.mesh.primitive_monkey_add(size=2.0, location=(3, 1.5, -0.5))
suzanne = bpy.context.active_object

# S-curve / Arc across Suzanne
curve_points_2d = [
    Vector((400, 300)),
    Vector((650, 520)),
    Vector((960, 640)),
    Vector((1280, 520)),
    Vector((1520, 740)),
]

from model_splitter.core.cutter_geometry import (
    resample_smooth_curve_2d,
    unproject_screen_to_object_plane,
)
from model_splitter.utils.math_utils import get_world_bounds
from mathutils.bvhtree import BVHTree

settings.cut.editable_points = 20
settings.connector.count = 3

curved_cutter, c_center, c_normal, c_mat = create_cutter_from_screen_curve(
    bpy.context,
    suzanne,
    curve_points_2d,
    mock_region,
    mock_rv3d,
)
assert curved_cutter is not None, "Curved cutter is None!"

# Enter Draft Mode (just like draw_cut_ops.py does!)
enter_draft_mode(bpy.context, suzanne, cut_type='CURVED', existing_cutter=curved_cutter)

# Verify child visual surface exists
vis_children = [ch for ch in curved_cutter.children if "Cut_Plane_Visual" in ch.name]
assert len(vis_children) == 1, f"Expected 1 MS_Cut_Plane_Visual child on curved cutter, got {len(vis_children)}"
vis_surf = vis_children[0]

# Build world-space BVHTree of the visual cutting surface
world_verts = [vis_surf.matrix_world @ v.co for v in vis_surf.data.vertices]
world_polys = [tuple(p.vertices) for p in vis_surf.data.polygons]
surf_bvh_world = BVHTree.FromPolygons(world_verts, world_polys)

# Verify every unprojected 3D point of the smoothed 2D curve lies on the world-space cutting surface!
_, _, suz_center, _ = get_world_bounds(suzanne)
view_normal = mock_rv3d.view_rotation @ Vector((0, 0, -1))
expected_2d = resample_smooth_curve_2d(curve_points_2d, num_samples=48)
expected_3d = [
    unproject_screen_to_object_plane(mock_region, mock_rv3d, pt, suz_center, view_normal)
    for pt in expected_2d
]

max_curve_err = 0.0
for pt3d in expected_3d:
    nearest_loc, _, _, dist = surf_bvh_world.find_nearest(pt3d)
    assert dist is not None and dist < 1e-4, f"Curve point {pt3d} deviated from cutting surface by {dist}!"
    max_curve_err = max(max_curve_err, dist)

print(f"[TEST-DRAW] Curved cutting surface matches drawn curve in world space! Max error = {max_curve_err:.2e}")

# Verify all 3 preview pins are snapped onto the curved cutting surface AND strictly inside Suzanne!
from model_splitter.core.cutter_geometry import is_point_inside_bvh
suz_verts_world = [suzanne.matrix_world @ v.co for v in suzanne.data.vertices]
suz_polys = [tuple(p.vertices) for p in suzanne.data.polygons]
suz_bvh_world = BVHTree.FromPolygons(suz_verts_world, suz_polys)

draft_col = bpy.data.collections.get("ModelSplitter_Draft")
pin_previews = [obj for obj in draft_col.objects if obj.name.endswith("_Pin")]
assert len(pin_previews) == 3, f"Expected 3 pin previews, got {len(pin_previews)}"
for pin_obj in pin_previews:
    pin_pos = pin_obj.matrix_world.translation
    _, _, _, pin_dist = surf_bvh_world.find_nearest(pin_pos)
    assert pin_dist < 1e-3, f"Pin {pin_obj.name} at {pin_pos} floated off curved surface by {pin_dist}!"
    assert is_point_inside_bvh(suz_bvh_world, pin_pos), f"Pin {pin_obj.name} at {pin_pos} was placed outside Suzanne!"

print("[TEST-DRAW] All 3 pins snapped accurately onto the curved cutting surface AND strictly inside Suzanne's cross-section!")

# Apply the curved draft build
suz_parts = apply_draft_build(bpy.context)
print(f"[TEST-DRAW] Curved cut build applied: {[p.name for p in suz_parts]}")
assert len(suz_parts) >= 2, "Curved draft build failed to split Suzanne!"

# 8. Test 3D Surface Contour Cut (Manual Cut)
print("[TEST-DRAW] Testing 3D Surface Contour Cut (Manual Mode)...")
bpy.ops.mesh.primitive_cube_add(size=2.0, location=(-3, 0, 0))
cube = bpy.context.active_object

# Closed 3D polygon contour on surface
surface_pts = [
    Vector((-4.0, -1.0, 0.0)),
    Vector((-2.0, -1.0, 0.0)),
    Vector((-2.0, 1.0, 0.0)),
    Vector((-4.0, 1.0, 0.0)),
]

surface_cutter, s_center, s_normal, s_mat = create_cutter_from_surface_points(
    bpy.context,
    cube,
    surface_pts,
)
assert surface_cutter is not None, "Surface cutter is None!"
assert surface_cutter.get("ms_is_thin_blade") is True, "Manual cutter should be a thin blade (no cylinder)!"
z_span_cutter = max(v.co.z for v in surface_cutter.data.vertices) - min(v.co.z for v in surface_cutter.data.vertices)
assert z_span_cutter < 0.02, f"Manual cutter should be a flat wafer plane, not a cylinder! Got Z thickness {z_span_cutter}"
vis_manual = [ch for ch in surface_cutter.children if "Cut_Plane_Visual" in ch.name][0]
assert len(vis_manual.data.polygons) == 640, f"Expected 640 smooth radial faces, got {len(vis_manual.data.polygons)}"
assert all(p.use_smooth for p in vis_manual.data.polygons), "Expected all visual cutting plane faces to be smooth-shaded!"
print(f"[TEST-DRAW] Surface contour cutter created: {surface_cutter.name} (thin blade Z={z_span_cutter:.5f}, NO cylinder) with {len(vis_manual.data.polygons)} smooth faces")

enter_draft_mode(bpy.context, cube, cut_type='MANUAL', existing_cutter=surface_cutter)
cube_parts = apply_draft_build(bpy.context)
print(f"[TEST-DRAW] Surface contour cut split: {[p.name for p in cube_parts]}")
assert len(cube_parts) >= 2, "Surface contour boolean cut failed!"

# 9. Test Sequential Second Cut with Asymmetric Stroke (Verifying Pins at the New Cut!)
print("[TEST-DRAW] Testing Sequential Second Cut with asymmetric mouse stroke...")
target_part = cube_parts[0]
bpy.ops.object.select_all(action='DESELECT')
target_part.select_set(True)
bpy.context.view_layer.objects.active = target_part

settings.connector.count = 2
settings.connector.target_side = 'PART_A'
settings.cut.explode_distance_mm = 0.0

# Asymmetric stroke: starts way off to the left (x=50) and ends just past the cube (x=1150)
asym_p1 = Vector((50, 580))
asym_p2 = Vector((1150, 580))
second_cutter, _, sec_center, _, _ = create_cutter_from_screen_line(
    bpy.context, target_part, asym_p1, asym_p2, mock_region, mock_rv3d
)
enter_draft_mode(bpy.context, target_part, cut_type='STRAIGHT', existing_cutter=second_cutter)

part_verts_w = [target_part.matrix_world @ v.co for v in target_part.data.vertices]
part_polys = [tuple(p.vertices) for p in target_part.data.polygons]
part_bvh_w = BVHTree.FromPolygons(part_verts_w, part_polys)

draft_col = bpy.data.collections.get("ModelSplitter_Draft")
sec_pins = [obj for obj in draft_col.objects if obj.name.endswith("_Pin")]
assert len(sec_pins) == 2, f"Expected 2 pins on second cut, got {len(sec_pins)}"
for p_obj in sec_pins:
    p_pos = p_obj.matrix_world.translation
    assert is_point_inside_bvh(part_bvh_w, p_pos), f"Second cut pin {p_obj.name} at {p_pos} is outside target_part!"
    # Verify determinant is positive (+1) so Exact Boolean normals are never inverted
    det = p_obj.matrix_world.to_3x3().determinant()
    assert det > 0.99, f"Pin matrix determinant is negative ({det}), which inverts boolean normals!"

print("[TEST-DRAW] Second cut pins are strictly inside the new cut cross-section with positive normal orientation!")
sec_results = apply_draft_build(bpy.context)
assert len(sec_results) >= 2, "Second cut failed!"
print(f"[TEST-DRAW] Second cut generated: {[p.name for p in sec_results]}")

# 10. Test Sparse & Dense 3D Manual Cut Around Subdivided Suzanne's Curved Ear Crease
print("[TEST-DRAW] Testing Sparse & Dense 3D Manual Cut around Suzanne's curved ear crease...")
import math
from model_splitter.core.boolean_ops import _find_face_components

for num_clicks in (5, 6, 8):
    bpy.ops.mesh.primitive_monkey_add(size=2.0, location=(6.0 * num_clicks, 0, 0))
    suz_ear = bpy.context.active_object
    mod = suz_ear.modifiers.new("Subsurf", 'SUBSURF')
    mod.levels = 2
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.context.view_layer.update()

    verts_w = [suz_ear.matrix_world @ v.co for v in suz_ear.data.vertices]
    polys = [tuple(p.vertices) for p in suz_ear.data.polygons]
    ear_bvh = BVHTree.FromPolygons(verts_w, polys)

    base_x = 6.0 * num_clicks
    ear_verts = [v for v in verts_w if v.x > base_x + 0.82]
    min_y = min(v.y for v in ear_verts)
    max_y = max(v.y for v in ear_verts)
    min_z = min(v.z for v in ear_verts)
    max_z = max(v.z for v in ear_verts)
    mid_y = 0.5 * (min_y + max_y)
    mid_z = 0.5 * (min_z + max_z)
    rad_y = 0.5 * (max_y - min_y)
    rad_z = 0.5 * (max_z - min_z)

    pts_3d = []
    for i in range(num_clicks):
        angle = (2.0 * math.pi * i) / num_clicks
        probe = Vector((base_x + 0.83, mid_y + math.cos(angle) * rad_y * 0.95, mid_z + math.sin(angle) * rad_z * 0.95))
        loc, _, _, _ = ear_bvh.find_nearest(probe)
        pts_3d.append(loc)

    ear_cutter, _, _, _ = create_cutter_from_surface_points(bpy.context, suz_ear, pts_3d)
    enter_draft_mode(bpy.context, suz_ear, cut_type='MANUAL', existing_cutter=ear_cutter)
    ear_results = apply_draft_build(bpy.context)
    assert len(ear_results) == 2, f"Expected 2 cleanly separated parts for {num_clicks}-click ear cut, got {len(ear_results)}"
    head_comps = _find_face_components(ear_results[0].data)
    ear_comps = _find_face_components(ear_results[1].data)
    if len(head_comps) != 3:
        for hc_f, hc_v in head_comps:
            if len(hc_f) < 100:
                pts_hc = [ear_results[0].matrix_world @ ear_results[0].data.vertices[vi].co for vi in hc_v]
                avg_hc = sum(pts_hc, Vector()) / len(pts_hc)
                # Find distance from avg_hc to ear_results[0] main component and ear_results[1]!
                print(f"  66-face pin centroid world={avg_hc}")
    assert len(head_comps) == 3, f"Expected 3 connected components in head (head + 2 eyes), got {[len(c[0]) for c in head_comps]}"
    assert len(ear_comps) == 1, f"Expected 1 connected component in severed ear, got {[len(c[0]) for c in ear_comps]}"
    print(f"[TEST-DRAW] {num_clicks}-click Manual ear cut cleanly separated Head ({len(ear_results[0].data.polygons)} tris/quads) and Ear ({len(ear_results[1].data.polygons)} tris/quads)!")


print("\n>>> ALL DRAWING CUT TESTS PASSED WITH 100% SUCCESS! <<<")

