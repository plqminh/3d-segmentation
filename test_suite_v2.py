"""
ModelSplitter Comprehensive Test Suite v2
Validates all features from the TTMinimal Split upgrade in Blender 5.1.
"""

import sys
import os
import math
import bpy
import bmesh
from mathutils import Vector

# Add addon directory to sys.path
addon_dir = os.path.dirname(__file__)
if addon_dir not in sys.path:
    sys.path.insert(0, addon_dir)

import model_splitter


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def run_tests():
    print("=" * 60)
    print("RUNNING MODELSPLITTER COMPREHENSIVE TEST SUITE")
    print("=" * 60)

    # 1. Register Addon
    print("\n[TEST 1] Registering ModelSplitter...")
    model_splitter.register()
    assert hasattr(bpy.types.Scene, "model_splitter"), "model_splitter property not registered on Scene!"
    print("PASS: Addon registered cleanly.")

    # 2. Test Scale Master & Transform Tools
    print("\n[TEST 2] Testing Scale Master...")
    reset_scene()
    bpy.ops.mesh.primitive_monkey_add(size=2.0, location=(5.0, 3.0, 1.0))
    suzanne = bpy.context.active_object
    assert suzanne is not None

    # Read dimensions
    bpy.ops.modelsplitter.read_dimensions()
    props = bpy.context.scene.model_splitter.scale_master
    print(f"Read dimensions: {props.dim_x_mm:.1f} x {props.dim_y_mm:.1f} x {props.dim_z_mm:.1f} mm")
    assert props.dim_x_mm > 0, "Dimension X should be > 0"

    # Scale to target 200 mm
    props.target_max_dim_mm = 200.0
    bpy.ops.modelsplitter.apply_dimensions(mode='UNIFORM_MAX')
    max_d = max(props.dim_x_mm, props.dim_y_mm, props.dim_z_mm)
    print(f"Scaled max dimension: {max_d:.2f} mm")
    assert abs(max_d - 200.0) < 1.0, f"Expected ~200mm max dimension, got {max_d}"

    # Center to origin
    bpy.ops.modelsplitter.center_origin()
    assert abs(suzanne.location.x) < 1e-4 and abs(suzanne.location.y) < 1e-4, "Object should be centered at (0, 0, Z)"

    # Drop to bed (Z=0)
    bpy.ops.modelsplitter.drop_to_bed()
    from model_splitter.utils.math_utils import get_world_bounds
    min_c, _, _, _ = get_world_bounds(suzanne)
    print(f"Lowest point Z after drop to bed: {min_c.z:.4f}")
    assert abs(min_c.z) < 1e-4, f"Lowest point should be at Z=0, got {min_c.z}"

    # Quick rotate
    bpy.ops.modelsplitter.quick_rotate(action='STAND')
    min_c2, _, _, _ = get_world_bounds(suzanne)
    assert abs(min_c2.z) < 1e-4, "Model should rest at Z=0 after rotation"
    print("PASS: Scale Master operations passed.")

    # 3. Test Fuse / Boolean Union
    print("\n[TEST 3] Testing Fuse Models (Boolean Union)...")
    reset_scene()
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 0))
    cube1 = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(1.0, 0, 0))
    cube2 = bpy.context.active_object
    cube1.select_set(True)
    cube2.select_set(True)
    bpy.context.view_layer.objects.active = cube1

    bpy.ops.modelsplitter.union_join(method='BOOLEAN')
    assert len([o for o in bpy.data.objects if o.type == 'MESH']) == 1, "Should merge into 1 mesh object"
    print("PASS: Boolean Union fuse passed.")

    # 4. Test Plane Cut with Magnet Connectors
    print("\n[TEST 4] Testing Plane Cut with Magnet Connectors...")
    reset_scene()
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 1.0))
    sphere = bpy.context.active_object

    settings = bpy.context.scene.model_splitter
    settings.cut.workflow_mode = 'EASY'
    settings.connector.shape = 'MAGNET'
    settings.connector.magnet_preset = '5x2'
    settings.connector.count = 1

    bpy.ops.modelsplitter.plane_cut()
    parts = [o for o in bpy.data.objects if o.type == 'MESH' and ("_Part_" in o.name)]
    print(f"Generated {len(parts)} parts from Plane Cut with Magnet slot.")
    assert len(parts) >= 2, f"Expected at least 2 parts, got {len(parts)}"
    print("PASS: Plane Cut with Magnet slots passed.")

    # 5. Test D-Pin Connectors
    print("\n[TEST 5] Testing D-Pin Keyed Connectors...")
    reset_scene()
    bpy.ops.mesh.primitive_cylinder_add(radius=1.0, depth=3.0, location=(0, 0, 1.5))
    cyl = bpy.context.active_object

    settings = bpy.context.scene.model_splitter
    settings.cut.workflow_mode = 'EASY'
    settings.connector.shape = 'D_PIN'
    settings.connector.count = 1
    settings.connector.diameter_mm = 6.0
    settings.connector.length_mm = 8.0

    bpy.ops.modelsplitter.straight_cut()
    d_parts = [o for o in bpy.data.objects if o.type == 'MESH' and ("_Part_" in o.name)]
    print(f"Generated {len(d_parts)} parts with D-Pin.")
    assert len(d_parts) >= 2, f"Expected at least 2 parts, got {len(d_parts)}"
    print("PASS: D-Pin cut passed.")

    # 6. Test Ball Joint Connectors
    print("\n[TEST 6] Testing Ball Joint Connectors...")
    reset_scene()
    bpy.ops.mesh.primitive_cylinder_add(radius=1.0, depth=3.0, location=(0, 0, 1.5))
    cyl = bpy.context.active_object

    settings = bpy.context.scene.model_splitter
    settings.cut.workflow_mode = 'EASY'
    settings.connector.shape = 'BALL_JOINT'
    settings.connector.count = 1

    bpy.ops.modelsplitter.straight_cut()
    b_parts = [o for o in bpy.data.objects if o.type == 'MESH' and ("_Part_" in o.name)]
    print(f"Generated {len(b_parts)} parts with Ball Joint.")
    assert len(b_parts) >= 2, f"Expected at least 2 parts, got {len(b_parts)}"
    print("PASS: Ball Joint cut passed.")

    # 7. Test Voxel Remesh and Decimate
    print("\n[TEST 7] Testing Voxel Remesh & Decimation...")
    reset_scene()
    bpy.ops.mesh.primitive_monkey_add(size=2.0)
    monkey = bpy.context.active_object
    orig_faces = len(monkey.data.polygons)

    # Remesh
    settings = bpy.context.scene.model_splitter
    settings.mesh_tools.remesh_voxel_size_mm = 0.8
    bpy.ops.modelsplitter.voxel_remesh()
    remesh_faces = len(monkey.data.polygons)
    print(f"Voxel Remesh faces: {orig_faces} -> {remesh_faces}")
    assert remesh_faces > 0, "Remesh should produce non-empty geometry"

    # Decimate
    settings.mesh_tools.decimate_ratio = 0.3
    bpy.ops.modelsplitter.decimate()
    decim_faces = len(monkey.data.polygons)
    print(f"Decimated faces: {remesh_faces} -> {decim_faces}")
    assert decim_faces < remesh_faces, f"Expected face reduction from {remesh_faces}, got {decim_faces}"
    print("PASS: Remesh & Decimation passed.")

    # 8. Test 3D Print Bed View & Auto-Packing
    print("\n[TEST 8] Testing 3D Print Bed View & Packing...")
    reset_scene()
    # Add 3 separate test parts
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(10, 0, 0))
    p1 = bpy.context.active_object
    bpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=1.0, location=(-10, 0, 0))
    p2 = bpy.context.active_object
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.6, location=(0, 10, 0))
    p3 = bpy.context.active_object

    p1.select_set(True)
    p2.select_set(True)
    p3.select_set(True)

    # Toggle print bed
    bpy.ops.modelsplitter.toggle_print_bed()
    bed_obj = bpy.data.objects.get("MS_Print_Bed_Plate")
    assert bed_obj is not None, "Print bed wireframe object should exist"
    assert bed_obj.display_type == 'WIRE', "Print bed should be displayed as wireframe"

    # Pack on bed
    bpy.ops.modelsplitter.pack_print_bed()
    # Verify all parts rest at Z=0
    for p in [p1, p2, p3]:
        min_c, _, _, _ = get_world_bounds(p)
        assert abs(min_c.z) < 1e-4, f"Part {p.name} should rest at Z=0, got {min_c.z}"
    print("PASS: 3D Print Bed View and Packing passed.")

    # 9. Test Unregistration
    print("\n[TEST 9] Unregistering ModelSplitter...")
    model_splitter.unregister()
    assert not hasattr(bpy.types.Scene, "model_splitter"), "model_splitter property should be removed from Scene!"
    print("PASS: Unregistered cleanly.")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED SUCCESSFULLY! (100% VERIFIED)")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
