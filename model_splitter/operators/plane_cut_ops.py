"""
ModelSplitter - Plane Cut & Contour Edit Operators
Provides dedicated interactive planar cutting, cut plane selection,
quick plane re-alignment, and curve contour tweaking.
"""

import math
import bpy
from mathutils import Vector, Matrix
from ..core.draft_manager import enter_draft_mode, apply_draft_build, update_draft_connectors, rebuild_cutter_from_visual_surface
from ..core.cutter_geometry import get_cutter_visual_surface_obj
from ..utils.math_utils import get_world_bounds


class MODEL_SPLITTER_OT_plane_cut(bpy.types.Operator):
    """Cut model using an adjustable 3D plane with transform gizmo"""
    bl_idname = "modelsplitter.plane_cut"
    bl_label = "Plane Cut"
    bl_description = "Place an adjustable cutting plane in the 3D viewport to slice the model"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        settings = getattr(context.scene, "model_splitter", None)
        in_draft = settings.cut.is_in_draft if settings else False
        return obj is not None and obj.type == 'MESH' and not in_draft

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.model_splitter
        mode = settings.cut.workflow_mode

        if mode == 'EASY':
            enter_draft_mode(context, obj, cut_type='STRAIGHT')
            results = apply_draft_build(context)
            if results:
                self.report({'INFO'}, f"Plane cut applied: {len(results)} parts generated.")
            return {'FINISHED'}
        else:
            enter_draft_mode(context, obj, cut_type='STRAIGHT')
            # Ensure gizmo is enabled so user can immediately translate/rotate the plane
            for space in context.area.spaces:
                if space.type == 'VIEW_3D':
                    space.show_gizmo = True
                    space.show_gizmo_tool = True
            self.report({'INFO'}, "Plane Cut: Move and rotate the plane gizmo, then click 'Apply Cut (Build)'")
            return {'FINISHED'}


class MODEL_SPLITTER_OT_select_cutter(bpy.types.Operator):
    """Select the cutting plane so you can move and rotate it with the 3D gizmo or G/R/S keys"""
    bl_idname = "modelsplitter.select_cutter"
    bl_label = "Select Cut Plane"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "model_splitter", None)
        return settings and settings.cut.is_in_draft

    def execute(self, context):
        settings = context.scene.model_splitter
        cut_props = settings.cut
        cutter_obj = bpy.data.objects.get(cut_props.active_cutter_name)
        if not cutter_obj:
            self.report({'WARNING'}, "No active cutting plane found in Draft Mode.")
            return {'CANCELLED'}

        # In edit mode, switch back to object mode first
        if context.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass

        bpy.ops.object.select_all(action='DESELECT')
        cutter_obj.select_set(True)
        context.view_layer.objects.active = cutter_obj

        # Enable viewport transform gizmo
        for space in context.area.spaces:
            if space.type == 'VIEW_3D':
                space.show_gizmo = True
                space.show_gizmo_tool = True

        self.report({'INFO'}, f"Selected '{cutter_obj.name}'. Use Gizmo or G/R/S to move and rotate.")
        return {'FINISHED'}


class MODEL_SPLITTER_OT_plane_align(bpy.types.Operator):
    """Quickly align the cutting plane position or orientation"""
    bl_idname = "modelsplitter.plane_align"
    bl_label = "Align Plane"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(
        items=[
            ('CENTER', "Center on Model", "Move plane to center of the active model"),
            ('HORIZONTAL', "Level Horizontal", "Align plane horizontally (Z normal up)"),
            ('VERTICAL_X', "Vertical X", "Align plane vertically along X"),
            ('VERTICAL_Y', "Vertical Y", "Align plane vertically along Y"),
            ('INVERT', "Invert Cut Side (180°)", "Rotate plane 180 degrees to flip which half is preserved"),
        ],
        default='CENTER',
    )

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "model_splitter", None)
        return settings and settings.cut.is_in_draft

    def execute(self, context):
        settings = context.scene.model_splitter
        cut_props = settings.cut
        cutter_obj = bpy.data.objects.get(cut_props.active_cutter_name)
        source_obj = bpy.data.objects.get(cut_props.active_source_name)

        if not cutter_obj or not source_obj:
            return {'CANCELLED'}

        if self.action == 'CENTER':
            _, _, center, _ = get_world_bounds(source_obj)
            cutter_obj.location = center
        elif self.action == 'HORIZONTAL':
            cutter_obj.rotation_euler = (0.0, 0.0, cutter_obj.rotation_euler.z)
        elif self.action == 'VERTICAL_X':
            cutter_obj.rotation_euler = (0.0, math.radians(90.0), 0.0)
        elif self.action == 'VERTICAL_Y':
            cutter_obj.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        elif self.action == 'INVERT':
            cutter_obj.rotation_euler.x += math.radians(180.0)

        context.view_layer.update()
        update_draft_connectors(context)
        return {'FINISHED'}


class MODEL_SPLITTER_OT_edit_contour(bpy.types.Operator):
    """Toggle interactive curve editing mode to tweak or add points with Ctrl+Click"""
    bl_idname = "modelsplitter.edit_contour"
    bl_label = "Edit Cut Contour"
    bl_description = "Enter/Exit Edit Mode on the active cutter curve to adjust or add points (Ctrl+Click)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "model_splitter", None)
        return settings and settings.cut.is_in_draft

    def execute(self, context):
        settings = context.scene.model_splitter
        cut_props = settings.cut
        cutter_obj = bpy.data.objects.get(cut_props.active_cutter_name)

        if not cutter_obj:
            self.report({'WARNING'}, "No active cutter found in Draft Mode.")
            return {'CANCELLED'}

        vis_obj = get_cutter_visual_surface_obj(cutter_obj)
        target_obj = vis_obj or cutter_obj

        if context.mode == 'EDIT_MESH':
            # Finish editing
            bpy.ops.object.mode_set(mode='OBJECT')
            cut_props.is_editing_contour = False
            target_obj.data.update()
            rebuild_cutter_from_visual_surface(cutter_obj)
            update_draft_connectors(context)
            self.report({'INFO'}, "Finished contour editing. Cutter and connectors updated!")
        else:
            # Enter edit mode on target
            bpy.ops.object.select_all(action='DESELECT')
            target_obj.select_set(True)
            context.view_layer.objects.active = target_obj
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            cut_props.is_editing_contour = True
            self.report({'INFO'}, "Contour Edit Mode: Adjust points or Ctrl+Click to add points, then click 'Finish Edit'")

        return {'FINISHED'}


classes = (
    MODEL_SPLITTER_OT_plane_cut,
    MODEL_SPLITTER_OT_select_cutter,
    MODEL_SPLITTER_OT_plane_align,
    MODEL_SPLITTER_OT_edit_contour,
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
