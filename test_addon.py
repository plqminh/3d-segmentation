"""
Test script for ModelSplitter in Blender background mode.
"""

import sys
import os
import bpy

# Add directory containing model_splitter to sys.path
workspace_dir = r"e:\3D segmentation"
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

print("[TEST] Importing model_splitter...")
try:
    import model_splitter
    model_splitter.register()
    print("[TEST] model_splitter registered successfully!")
except Exception as e:
    print(f"[TEST ERROR] Failed to register: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Ensure clean scene
bpy.ops.wm.read_factory_settings(use_empty=True)

# 1. Test Mesh Creation
print("[TEST] Creating test Suzanne monkey mesh...")
bpy.ops.mesh.primitive_monkey_add(size=2.0, location=(0, 0, 0))
obj = bpy.context.active_object
print(f"[TEST] Created object: {obj.name}, verts: {len(obj.data.vertices)}, faces: {len(obj.data.polygons)}")

# 2. Test Mesh Diagnostics
print("[TEST] Running mesh health diagnostics...")
bpy.ops.modelsplitter.check_mesh()
mesh_check = bpy.context.scene.model_splitter.mesh_check
print(f"[TEST] Mesh status: {mesh_check.status_message}")
print(f"[TEST] Non-manifold: {mesh_check.non_manifold_count}, Holes: {mesh_check.open_edges_count}")

# 3. Test Solid Cube (perfect manifold for cut)
print("[TEST] Creating solid test UV sphere...")
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 0))
sphere = bpy.context.active_object
bpy.context.view_layer.objects.active = sphere

# 4. Test Draft Mode Setup
print("[TEST] Entering Draft Mode for Straight Cut...")
settings = bpy.context.scene.model_splitter
settings.cut.workflow_mode = 'DRAFT'
settings.connector.shape = 'CYLINDER'
settings.connector.count = 2
settings.connector.diameter_mm = 6.0
settings.connector.length_mm = 12.0
settings.connector.clearance_mm = 0.25

bpy.ops.modelsplitter.straight_cut()
print(f"[TEST] In draft: {settings.cut.is_in_draft}")
print(f"[TEST] Active cutter: {settings.cut.active_cutter_name}")

# Verify cutter and preview pins exist
draft_col = bpy.data.collections.get("ModelSplitter_Draft")
assert draft_col is not None, "Draft collection missing!"
print(f"[TEST] Objects in draft collection: {[o.name for o in draft_col.objects]}")

# 5. Test Settings Update (change to Conical, 3 pins)
print("[TEST] Updating connector settings to Conical, 3 pins...")
settings.connector.shape = 'CONICAL'
settings.connector.count = 3
bpy.ops.modelsplitter.update_draft_preview()
print(f"[TEST] Objects in draft after update: {[o.name for o in draft_col.objects]}")

# 6. Test Finalize / Build
print("[TEST] Applying cut (Build)...")
bpy.ops.modelsplitter.apply_build()
print(f"[TEST] In draft after build: {settings.cut.is_in_draft}")

# Check resulting objects
resulting_objs = [o for o in bpy.data.objects if o.type == 'MESH' and not o.hide_viewport]
print(f"[TEST] Resulting mesh objects: {[o.name for o in resulting_objs]}")
for o in resulting_objs:
    print(f"  -> Object '{o.name}': {len(o.data.vertices)} verts, {len(o.data.polygons)} faces")

# 7. Test Batch Export
export_dir = os.path.join(workspace_dir, "test_exports")
settings.export.export_dir = export_dir
settings.export.format = 'STL'

print(f"[TEST] Testing batch STL export to {export_dir}...")
# Select parts
for o in resulting_objs:
    o.select_set(True)
bpy.ops.modelsplitter.batch_export()

if os.path.exists(export_dir):
    files = os.listdir(export_dir)
    print(f"[TEST] Exported files: {files}")
    assert len(files) > 0, "No files exported!"

# 8. Test Double-Sided Loose Dowel Pins + Cut Gap + Live Explode & Collapse
print("\n[TEST] Testing Double-Sided Loose Dowel Pins, Cut Gap (0.5mm), and Live Explode...")
bpy.ops.mesh.primitive_cylinder_add(radius=1.0, depth=2.0, location=(5.0, 0.0, 0.0))
cyl = bpy.context.active_object
bpy.context.view_layer.objects.active = cyl

settings.cut.workflow_mode = 'DRAFT'
settings.connector.shape = 'CYLINDER'
settings.connector.count = 2
settings.connector.diameter_mm = 5.0
settings.connector.length_mm = 10.0
settings.connector.clearance_mm = 0.2
settings.connector.cut_gap_mm = 0.5
settings.connector.double_sided = True
settings.cut.explode_distance_mm = 20.0

bpy.ops.modelsplitter.straight_cut()
bpy.ops.modelsplitter.apply_build()

dowel_objs = [o for o in bpy.data.objects if "_Dowel_" in o.name]
cyl_part_a = bpy.data.objects.get("Cylinder_Part_A")
cyl_part_b = bpy.data.objects.get("Cylinder_Part_B")
assert cyl_part_a is not None and cyl_part_b is not None, "Cylinder Part A/B missing!"
assert len(dowel_objs) == 2, f"Expected 2 loose dowel objects when double_sided=True, got {len(dowel_objs)}"
print(f"[TEST] Created double-sided dowels: {[d.name for d in dowel_objs]}")

# Verify live Explode Preview moved Part B by full offset and Dowels by 0.5 * offset
assert cyl_part_b.location.z > 0.1, f"Expected Part B to be exploded in +Z, got {cyl_part_b.location.z}"
assert abs(dowel_objs[0].location.z - cyl_part_b.location.z * 0.5) < 1e-4, "Dowel should float halfway between Part A and Part B!"

# Collapse explode via operator and verify parts snap back to base location
bpy.ops.modelsplitter.reset_explode()
assert abs(cyl_part_b.location.z) < 1e-5, f"Expected Part B Z=0 after reset_explode, got {cyl_part_b.location.z}"

# Verify Cut Gap (0.5mm -> 0.01 BU at scale 50) created a real physical gap between Part A and Part B!
from model_splitter.utils.math_utils import mm_to_scene_units
expected_gap = mm_to_scene_units(bpy.context, 0.5, ref_obj=cyl_part_a)
max_z_a = max((cyl_part_a.matrix_world @ v.co).z for v in cyl_part_a.data.vertices)
min_z_b = min((cyl_part_b.matrix_world @ v.co).z for v in cyl_part_b.data.vertices)
actual_gap = min_z_b - max_z_a
print(f"[TEST] Cut Gap verification: expected={expected_gap:.5f}, actual={actual_gap:.5f}")
assert abs(actual_gap - expected_gap) < 1e-3, f"Cut gap mismatch: expected {expected_gap}, got {actual_gap}"

# 9. Test Manual Pin Placement Mode (Preserves custom dragged pin positions)
print("\n[TEST] Testing Manual Pin Placement Mode...")
settings.connector.double_sided = False
settings.connector.cut_gap_mm = 0.0
settings.connector.count = 1
settings.connector.placement_mode = 'MANUAL'

bpy.ops.mesh.primitive_cube_add(size=2.0, location=(10.0, 0.0, 0.0))
man_cube = bpy.context.active_object
bpy.context.view_layer.objects.active = man_cube

bpy.ops.modelsplitter.straight_cut()
draft_col = bpy.data.collections.get("ModelSplitter_Draft")
pin_prev = [o for o in draft_col.objects if o.name.endswith("_Pin")][0]

# Simulate user dragging the pin to local X = +0.42, Y = -0.31 in the viewport
pin_prev.location.x = 0.42
pin_prev.location.y = -0.31
bpy.context.view_layer.update()

# Trigger a parameter update (change diameter) and verify MANUAL mode preserves the dragged XY offset!
settings.connector.diameter_mm = 6.0
bpy.ops.modelsplitter.update_draft_preview()
pin_prev_after = [o for o in draft_col.objects if o.name.endswith("_Pin")][0]
print(f"[TEST] Manual pin local pos after update: ({pin_prev_after.location.x:.3f}, {pin_prev_after.location.y:.3f})")
assert abs(pin_prev_after.location.x - 0.42) < 1e-3 and abs(pin_prev_after.location.y - (-0.31)) < 1e-3, (
    "Manual pin placement was overwritten by update_draft_preview!"
)

# Test Reset Pin Positions operator
bpy.ops.modelsplitter.reset_pin_positions()
pin_prev_reset = [o for o in draft_col.objects if o.name.endswith("_Pin")][0]
assert abs(pin_prev_reset.location.x) < 0.05 and abs(pin_prev_reset.location.y) < 0.05, "reset_pin_positions did not re-center pin!"
bpy.ops.modelsplitter.cancel_draft()
settings.connector.placement_mode = 'AUTO'

# 10. Test Separate from Base Operator (Auto pedestal step detection)
print("\n[TEST] Testing Separate from Base operator...")
bpy.ops.mesh.primitive_cylinder_add(radius=1.2, depth=0.4, location=(15.0, 0.0, 0.2))
pedestal = bpy.context.active_object
bpy.ops.mesh.primitive_cylinder_add(radius=0.45, depth=1.6, location=(15.0, 0.0, 1.2))
figure_col = bpy.context.active_object
from model_splitter.core.boolean_ops import apply_boolean_modifier
apply_boolean_modifier(pedestal, figure_col, operation='UNION', solver='EXACT')
bpy.data.objects.remove(figure_col, do_unlink=True)
bpy.context.view_layer.objects.active = pedestal

bpy.ops.modelsplitter.separate_base()
base_cutter = bpy.data.objects.get(settings.cut.active_cutter_name)
detected_z = base_cutter.matrix_world.translation.z
print(f"[TEST] Separate from Base detected pedestal top at Z={detected_z:.3f} (true step Z=0.400)")
assert 0.32 <= detected_z <= 0.48, f"Expected base cutter near Z=0.40, got {detected_z}"
base_parts = bpy.ops.modelsplitter.apply_build()

# 11. Test Holes Only (No Pins) Mode
print("\n[TEST] Testing Holes Only (No Pins) Mode...")
bpy.ops.mesh.primitive_cube_add(size=2.0, location=(25.0, 0.0, 0.0))
holes_cube = bpy.context.active_object
bpy.context.view_layer.objects.active = holes_cube

settings.connector.count = 1
settings.connector.diameter_mm = 10.0
settings.connector.length_mm = 15.0
settings.connector.double_sided = False
settings.connector.holes_only = True
settings.cut.explode_distance_mm = 0.0

bpy.ops.modelsplitter.straight_cut()
draft_col = bpy.data.collections.get("ModelSplitter_Draft")
hole_previews = [o for o in draft_col.objects if o.name.endswith("_Pin")]
assert len(hole_previews) == 1 and hole_previews[0].display_type == 'WIRE', (
    "Holes Only preview should display as WIRE (no solid green pin)!"
)

from model_splitter.core.draft_manager import apply_draft_build
holes_results = apply_draft_build(bpy.context)
print(f"[TEST] Holes Only generated parts: {[p.name for p in holes_results]}")
assert len(holes_results) == 2, f"Expected exactly 2 parts (no loose dowels) in Holes Only mode, got {len(holes_results)}"
assert not any("Dowel" in p.name for p in holes_results), "No dowels should be created in Holes Only mode!"

# Both Part A and Part B of a 6-face cube must have socket holes carved into them (> 20 faces each, no protruding Z bounds)
for hp in holes_results:
    poly_cnt = len(hp.data.polygons)
    print(f"[TEST] {hp.name} polygon count with carved socket hole: {poly_cnt}")
    assert poly_cnt > 20, f"Expected socket hole carved into {hp.name}, but only has {poly_cnt} polygons!"

# Part A occupies Z in [-1, 0] and Part B occupies Z in [0, 1] -> neither should have a male pin protruding past Z=0!
part_a_max_z = max((holes_results[0].matrix_world @ v.co).z for v in holes_results[0].data.vertices)
part_b_min_z = min((holes_results[1].matrix_world @ v.co).z for v in holes_results[1].data.vertices)
assert part_a_max_z <= 1e-4, f"Part A has a protruding male pin (max Z = {part_a_max_z:.4f}) in Holes Only mode!"
assert part_b_min_z >= -1e-4, f"Part B has a protruding male pin (min Z = {part_b_min_z:.4f}) in Holes Only mode!"
settings.connector.holes_only = False

# 12. Test Curve Detail Extrude
print("\n[TEST] Testing Curve Detail Extrude...")
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(40.0, 0.0, 0.0), segments=48, ring_count=24)
det_sphere = bpy.context.active_object
bpy.context.view_layer.objects.active = det_sphere
settings.connector.count = 1
settings.connector.holes_only = False
settings.cut.explode_distance_mm = 0.0
settings.cut.extrude_depth_mm = 50.0
settings.cut.curve_smoothness = 0.7
settings.cut.workflow_mode = 'EASY'

from model_splitter.core.cutter_geometry import create_editable_detail_curve
curve_obj = create_editable_detail_curve(bpy.context, det_sphere)
assert curve_obj.type == 'CURVE'
bpy.ops.object.select_all(action='DESELECT')
curve_obj.select_set(True)
bpy.context.view_layer.objects.active = curve_obj
res = bpy.ops.modelsplitter.extrude_curve_cut()
print(f"[TEST] extrude_curve_cut -> {res}")
detail_parts = [o for o in bpy.data.objects if o.name.startswith("Sphere") and "_Part_" in o.name and o.location.x > 30 or (o.name.startswith("Sphere.00") and "_Part_" in o.name)]
print(f"[TEST] Detail parts: {[o.name for o in detail_parts]}")
assert len(detail_parts) >= 2, "Curve detail extrude should produce body + detail parts!"
settings.cut.workflow_mode = 'DRAFT'


# Live smoothness change in Draft Mode
print("\n[TEST] Testing live curve smoothness in Draft Mode...")
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(80.0, 0.0, 0.0), segments=48, ring_count=24)
sm_sphere = bpy.context.active_object
bpy.context.view_layer.objects.active = sm_sphere
settings.cut.workflow_mode = 'DRAFT'
settings.cut.curve_smoothness = 0.0
sm_curve = create_editable_detail_curve(bpy.context, sm_sphere)
bpy.ops.object.select_all(action='DESELECT')
sm_curve.select_set(True)
bpy.context.view_layer.objects.active = sm_curve
bpy.ops.modelsplitter.extrude_curve_cut()
cut0 = bpy.data.objects.get(settings.cut.active_cutter_name)
n0 = len(cut0.data.vertices)
v0 = [tuple(v.co) for v in cut0.data.vertices][:5]
settings.cut.curve_smoothness = 1.0
cut1 = bpy.data.objects.get(settings.cut.active_cutter_name)
assert settings.cut.is_in_draft and cut1 is not None, "Draft lost after smoothness change!"
v1 = [tuple(v.co) for v in cut1.data.vertices][:5]
print(f"[TEST] cutter verts {n0} -> {len(cut1.data.vertices)}, changed={v0 != v1}")
assert v0 != v1, "Smoothness change did not rebuild the cutter!"
bpy.ops.modelsplitter.cancel_draft()
settings.cut.curve_smoothness = 0.0
settings.cut.workflow_mode = 'DRAFT'
# 13. Test No Pins option
print("\n[TEST] Testing No Pins option...")
bpy.ops.mesh.primitive_cube_add(size=2.0, location=(60.0, 0.0, 0.0))
np_cube = bpy.context.active_object
bpy.context.view_layer.objects.active = np_cube
settings.connector.no_connectors = True
bpy.ops.modelsplitter.straight_cut()
draft_col = bpy.data.collections.get("ModelSplitter_Draft")
assert not [o for o in draft_col.objects if o.name.startswith("MS_Conn_")], "No connectors expected in draft!"
np_parts = bpy.ops.modelsplitter.apply_build()
np_objs = [o for o in bpy.data.objects if o.name.startswith("Cube.00") and "_Part_" in o.name and o.name.startswith(np_cube.name)]
assert all(len(o.data.polygons) == 6 for o in np_objs) and len(np_objs) == 2, [(o.name, len(o.data.polygons)) for o in np_objs]
settings.connector.no_connectors = False

print("\n>>> ALL TESTS PASSED SUCCESSFULLY! <<<")



