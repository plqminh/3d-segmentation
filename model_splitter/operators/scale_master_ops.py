"""
ModelSplitter - Scale Master & Model Transform Operators
Provides millimeter-based dimensioning, viewport framing, centering,
drop-to-bed (Z=0), boolean union merging, and quick 90-degree rotations.
"""

import math
import bpy
import bmesh
from mathutils import Vector, Matrix
from ..utils.math_utils import get_world_bounds, scene_units_to_mm, mm_to_scene_units


class MODEL_SPLITTER_OT_read_dimensions(bpy.types.Operator):
    """Read the active object's millimeter dimensions into Scale Master dials"""
    bl_idname = "modelsplitter.read_dimensions"
    bl_label = "Read Dimensions"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        _, _, _, dims = get_world_bounds(obj)
        scale_props = context.scene.model_splitter.scale_master

        scale_props.dim_x_mm = scene_units_to_mm(context, dims.x, ref_obj=obj)
        scale_props.dim_y_mm = scene_units_to_mm(context, dims.y, ref_obj=obj)
        scale_props.dim_z_mm = scene_units_to_mm(context, dims.z, ref_obj=obj)
        scale_props.target_max_dim_mm = max(scale_props.dim_x_mm, scale_props.dim_y_mm, scale_props.dim_z_mm)
        self.report({'INFO'}, f"Dimensions: {scale_props.dim_x_mm:.1f} x {scale_props.dim_y_mm:.1f} x {scale_props.dim_z_mm:.1f} mm")
        return {'FINISHED'}


class MODEL_SPLITTER_OT_apply_dimensions(bpy.types.Operator):
    """Scale the selected object to the target millimeter dimensions"""
    bl_idname = "modelsplitter.apply_dimensions"
    bl_label = "Apply Size"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        items=[
            ('UNIFORM_MAX', "Uniform Max", "Scale model uniformly so longest axis equals target size"),
            ('AXIS_XYZ', "Axis XYZ", "Scale along X, Y, Z axes"),
        ],
        default='UNIFORM_MAX',
    )

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        _, _, _, dims = get_world_bounds(obj)
        scale_props = context.scene.model_splitter.scale_master

        cur_x_mm = scene_units_to_mm(context, dims.x, ref_obj=obj)
        cur_y_mm = scene_units_to_mm(context, dims.y, ref_obj=obj)
        cur_z_mm = scene_units_to_mm(context, dims.z, ref_obj=obj)
        max_cur = max(cur_x_mm, cur_y_mm, cur_z_mm, 1e-6)

        if self.mode == 'UNIFORM_MAX' or scale_props.uniform_scale_lock:
            factor = scale_props.target_max_dim_mm / max_cur
            obj.scale *= factor
        else:
            fx = scale_props.dim_x_mm / max(cur_x_mm, 1e-6)
            fy = scale_props.dim_y_mm / max(cur_y_mm, 1e-6)
            fz = scale_props.dim_z_mm / max(cur_z_mm, 1e-6)
            obj.scale.x *= fx
            obj.scale.y *= fy
            obj.scale.z *= fz

        # Apply scale to geometry matrix
        context.view_layer.update()
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        # Update property dials
        bpy.ops.modelsplitter.read_dimensions()
        return {'FINISHED'}


class MODEL_SPLITTER_OT_reset_view(bpy.types.Operator):
    """Focus and fit the 3D viewport camera to the selected model"""
    bl_idname = "modelsplitter.reset_view"
    bl_label = "Reset View"

    def execute(self, context):
        if not context.selected_objects and context.active_object:
            context.active_object.select_set(True)
        try:
            bpy.ops.view3d.view_selected(use_all_regions=False)
        except Exception:
            pass
        return {'FINISHED'}


class MODEL_SPLITTER_OT_center_origin(bpy.types.Operator):
    """Center the model geometry and move it to world origin (0, 0, 0)"""
    bl_idname = "modelsplitter.center_origin"
    bl_label = "Center to Origin"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
        obj.location = Vector((0.0, 0.0, obj.location.z))
        obj.location.x = 0.0
        obj.location.y = 0.0
        return {'FINISHED'}


class MODEL_SPLITTER_OT_drop_to_bed(bpy.types.Operator):
    """Drop model onto ground plane so bottom sits flush at Z = 0"""
    bl_idname = "modelsplitter.drop_to_bed"
    bl_label = "Drop to Bed (Z=0)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        min_corner, _, _, _ = get_world_bounds(obj)
        # Shift down/up along Z so min_corner.z == 0.0
        obj.location.z -= min_corner.z
        return {'FINISHED'}


class MODEL_SPLITTER_OT_quick_rotate(bpy.types.Operator):
    """Quickly reorient model by 90 degrees to stand upright or lay flat"""
    bl_idname = "modelsplitter.quick_rotate"
    bl_label = "Quick Rotate"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(
        items=[
            ('STAND', "Stand Up", "Rotate 90 degrees around X to stand vertical"),
            ('LAY', "Lay Flat", "Rotate -90 degrees around X to lay flat"),
            ('TURN_Z', "Turn 90°", "Rotate 90 degrees around Z"),
        ],
        default='STAND',
    )

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        if self.action == 'STAND':
            obj.rotation_euler.x += math.radians(90.0)
        elif self.action == 'LAY':
            obj.rotation_euler.x -= math.radians(90.0)
        elif self.action == 'TURN_Z':
            obj.rotation_euler.z += math.radians(90.0)

        context.view_layer.update()
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        bpy.ops.modelsplitter.drop_to_bed()
        return {'FINISHED'}


class MODEL_SPLITTER_OT_union_join(bpy.types.Operator):
    """Merge selected objects into a single manifold mesh (Boolean Union / Join)"""
    bl_idname = "modelsplitter.union_join"
    bl_label = "Join Models"
    bl_options = {'REGISTER', 'UNDO'}

    method: bpy.props.EnumProperty(
        items=[
            ('BOOLEAN', "Boolean Union", "Carves and fuses overlapping shells into one seamless surface"),
            ('JOIN', "Direct Join", "Combines mesh data blocks into one object"),
        ],
        default='BOOLEAN',
    )

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) >= 2 and context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        active = context.active_object
        selected = [o for o in context.selected_objects if o.type == 'MESH' and o != active]

        if not selected:
            self.report({'WARNING'}, "Select at least 2 mesh objects to merge")
            return {'CANCELLED'}

        if self.method == 'BOOLEAN':
            for target in selected:
                mod = active.modifiers.new(name="MS_Union", type='BOOLEAN')
                mod.operation = 'UNION'
                mod.operand_type = 'OBJECT'
                mod.object = target
                mod.solver = 'EXACT'
                try:
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                except Exception:
                    mod.solver = 'FAST'
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                bpy.data.objects.remove(target, do_unlink=True)
            self.report({'INFO'}, "Successfully fused models via Boolean Union")
        else:
            bpy.ops.object.join()
            self.report({'INFO'}, "Successfully joined models")

        # Auto recalculate normals
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')

        bpy.ops.modelsplitter.read_dimensions()
        return {'FINISHED'}


class MODEL_SPLITTER_OT_toggle_gizmo(bpy.types.Operator):
    """Toggle 3D Viewport Transform Gizmo on/off"""
    bl_idname = "modelsplitter.toggle_gizmo"
    bl_label = "Toggle Gizmo"

    def execute(self, context):
        for space in context.area.spaces:
            if space.type == 'VIEW_3D':
                space.show_gizmo = not space.show_gizmo
                space.show_gizmo_tool = space.show_gizmo
                break
        return {'FINISHED'}


classes = (
    MODEL_SPLITTER_OT_read_dimensions,
    MODEL_SPLITTER_OT_apply_dimensions,
    MODEL_SPLITTER_OT_reset_view,
    MODEL_SPLITTER_OT_center_origin,
    MODEL_SPLITTER_OT_drop_to_bed,
    MODEL_SPLITTER_OT_quick_rotate,
    MODEL_SPLITTER_OT_union_join,
    MODEL_SPLITTER_OT_toggle_gizmo,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
