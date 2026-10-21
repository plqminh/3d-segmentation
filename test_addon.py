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

print("\n>>> ALL TESTS PASSED SUCCESSFULLY! <<<")
