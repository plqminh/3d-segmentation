"""
ModelSplitter - Straight and Curved Cut Operators
"""

import bpy
from ..core.draft_manager import enter_draft_mode, apply_draft_build


class MODEL_SPLITTER_OT_straight_cut(bpy.types.Operator):
    bl_idname = "modelsplitter.straight_cut"
    bl_label = "Straight Cut"
    bl_description = "Cut the model using a planar cutting surface"
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
            # Easy mode: Setup and apply in a single automated step
            holes_only = bool(getattr(settings.connector, "holes_only", False))
            enter_draft_mode(context, obj, cut_type='STRAIGHT')
            results = apply_draft_build(context)
            if results:
                suffix = "socket holes (no pins)" if holes_only else "pins"
                self.report({'INFO'}, f"Successfully split into {len(results)} parts with {suffix}!")
            else:
                self.report({'WARNING'}, "Cut operation produced no results. Check mesh manifoldness.")
            return {'FINISHED'}
        else:
            # Draft mode: Set up non-destructive preview
            enter_draft_mode(context, obj, cut_type='STRAIGHT')
            self.report({'INFO'}, "Draft Mode active: Move/rotate the cutting plane, then click 'Apply Cut (Build)'")
            return {'FINISHED'}


class MODEL_SPLITTER_OT_curved_cut(bpy.types.Operator):
    bl_idname = "modelsplitter.curved_cut"
    bl_label = "Curved Cut"
    bl_description = "Cut the model using an organic curved cutting surface"
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
            enter_draft_mode(context, obj, cut_type='CURVED')
            results = apply_draft_build(context)
            if results:
                self.report({'INFO'}, f"Curved cut finished: {len(results)} parts generated.")
            return {'FINISHED'}
        else:
            enter_draft_mode(context, obj, cut_type='CURVED')
            self.report({'INFO'}, "Draft Mode active: Adjust curved surface position, then click 'Apply Cut (Build)'")
            return {'FINISHED'}


class MODEL_SPLITTER_OT_separate_base(bpy.types.Operator):
    bl_idname = "modelsplitter.separate_base"
    bl_label = "Separate from Base"
    bl_description = "Auto-detects the figurine pedestal/base height and creates a horizontal cut with foot pegs"
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
            enter_draft_mode(context, obj, cut_type='SEPARATE_BASE')
            results = apply_draft_build(context)
            if results:
                self.report({'INFO'}, f"Separated base cleanly: {len(results)} parts generated.")
            return {'FINISHED'}
        else:
            enter_draft_mode(context, obj, cut_type='SEPARATE_BASE')
            self.report({'INFO'}, "Draft Mode active: Base cutter placed at detected pedestal height.")
            return {'FINISHED'}


class MODEL_SPLITTER_OT_add_detail_curve(bpy.types.Operator):
    bl_idname = "modelsplitter.add_detail_curve"
    bl_label = "Add Detail Curve"
    bl_description = "Adds an editable closed Bezier curve snapped onto the model surface; shape it around a detail, then extrude it into a Boolean cutter"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        settings = getattr(context.scene, "model_splitter", None)
        in_draft = settings.cut.is_in_draft if settings else False
        return obj is not None and obj.type == 'MESH' and not in_draft

    def execute(self, context):
        from ..core.cutter_geometry import create_editable_detail_curve
        src = context.active_object
        rv3d = getattr(context, "region_data", None)
        curve_obj = create_editable_detail_curve(context, src, rv3d=rv3d)
        bpy.ops.object.select_all(action='DESELECT')
        curve_obj.select_set(True)
        context.view_layer.objects.active = curve_obj
        self.report({'INFO'}, "Detail curve added. Edit its points (Tab), then click 'Extrude Curve to Cutter'.")
        return {'FINISHED'}


class MODEL_SPLITTER_OT_extrude_curve_cut(bpy.types.Operator):
    bl_idname = "modelsplitter.extrude_curve_cut"
    bl_label = "Extrude Curve to Cutter"
    bl_description = "Extrudes the selected closed curve into a polygon volume and Booleans the enclosed detail out of the model"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        settings = getattr(context.scene, "model_splitter", None)
        in_draft = settings.cut.is_in_draft if settings else False
        return obj is not None and obj.type == 'CURVE' and not in_draft

    def execute(self, context):
        from ..core.cutter_geometry import (
            extract_points_from_curve_object,
            create_extruded_curve_cutter_from_points,
        )
        curve_obj = context.active_object
        settings = context.scene.model_splitter

        src = bpy.data.objects.get(curve_obj.get("ms_source_obj", ""))
        if src is None or src.type != 'MESH':
            meshes = [o for o in context.selected_objects if o.type == 'MESH']
            src = meshes[0] if meshes else None
        if src is None:
            self.report({'ERROR'}, "No source mesh found. Select the mesh together with the curve, or use 'Add Detail Curve'.")
            return {'CANCELLED'}

        pts = extract_points_from_curve_object(context, curve_obj, source_obj=src)
        if len(pts) < 3:
            self.report({'ERROR'}, "Curve needs at least 3 points.")
            return {'CANCELLED'}

        cutter_obj, _, _, _ = create_extruded_curve_cutter_from_points(
            context, src, pts, extrude_depth_mm=settings.cut.extrude_depth_mm,
            smoothness=settings.cut.curve_smoothness,
        )

        enter_draft_mode(context, src, cut_type='EXTRUDE_CURVE', existing_cutter=cutter_obj)
        bpy.data.objects.remove(curve_obj, do_unlink=True)

        if settings.cut.workflow_mode == 'EASY':
            results = apply_draft_build(context)
            self.report({'INFO'}, f"Detail extracted: {len(results)} parts generated.")
        else:
            self.report({'INFO'}, "Draft Mode active: adjust Extrude Depth, then click 'Apply Cut (Build)'")
        return {'FINISHED'}


classes = (
    MODEL_SPLITTER_OT_straight_cut,
    MODEL_SPLITTER_OT_curved_cut,
    MODEL_SPLITTER_OT_separate_base,
    MODEL_SPLITTER_OT_add_detail_curve,
    MODEL_SPLITTER_OT_extrude_curve_cut,
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
