"""
ModelSplitter - Draft Mode Lifecycle Operators
"""

import bpy
from ..core.draft_manager import apply_draft_build, cancel_draft_mode, update_draft_connectors


class MODEL_SPLITTER_OT_apply_build(bpy.types.Operator):
    bl_idname = "modelsplitter.apply_build"
    bl_label = "Apply Cut (Build)"
    bl_description = "Bake cutting plane and generate alignment pins and sockets"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "model_splitter", None)
        return settings is not None and settings.cut.is_in_draft

    def execute(self, context):
        holes_only = bool(getattr(context.scene.model_splitter.connector, "holes_only", False))
        results = apply_draft_build(context)
        if results:
            suffix = "socket holes (no pins)" if holes_only else "pins"
            self.report({'INFO'}, f"Successfully split model into {len(results)} parts with {suffix}!")
        else:
            self.report({'ERROR'}, "Split operation failed. Ensure the cutting plane intersects the mesh.")
        return {'FINISHED'}


class MODEL_SPLITTER_OT_cancel_draft(bpy.types.Operator):
    bl_idname = "modelsplitter.cancel_draft"
    bl_label = "Cancel Cut"
    bl_description = "Cancel draft mode and discard temporary cutters and pins"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "model_splitter", None)
        return settings is not None and settings.cut.is_in_draft

    def execute(self, context):
        cancel_draft_mode(context)
        self.report({'INFO'}, "Draft mode cancelled.")
        return {'FINISHED'}


class MODEL_SPLITTER_OT_update_draft_preview(bpy.types.Operator):
    bl_idname = "modelsplitter.update_draft_preview"
    bl_label = "Update Preview"
    bl_description = "Refreshes connector previews to reflect modified parameters"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        update_draft_connectors(context)
        return {'FINISHED'}


class MODEL_SPLITTER_OT_snap_manual_pins(bpy.types.Operator):
    bl_idname = "modelsplitter.snap_manual_pins"
    bl_label = "Snap Pins to Surface"
    bl_description = "Snaps manually positioned pins directly onto the cutting surface with aligned normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "model_splitter", None)
        return settings is not None and settings.cut.is_in_draft

    def execute(self, context):
        update_draft_connectors(context, force_auto=False)
        self.report({'INFO'}, "Snapped pins to cutting surface.")
        return {'FINISHED'}


class MODEL_SPLITTER_OT_reset_pin_positions(bpy.types.Operator):
    bl_idname = "modelsplitter.reset_pin_positions"
    bl_label = "Reset Pin Positions"
    bl_description = "Resets connector pins to automatic symmetric positions inside the cut cross-section"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "model_splitter", None)
        return settings is not None and settings.cut.is_in_draft

    def execute(self, context):
        update_draft_connectors(context, force_auto=True)
        self.report({'INFO'}, "Reset pins to automatic symmetric placement.")
        return {'FINISHED'}


class MODEL_SPLITTER_OT_reset_explode(bpy.types.Operator):
    bl_idname = "modelsplitter.reset_explode"
    bl_label = "Collapse Explode"
    bl_description = "Resets Explode Preview distance to 0mm and snaps split parts back together"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.model_splitter.cut.explode_distance_mm = 0.0
        self.report({'INFO'}, "Collapsed exploded parts to 0mm.")
        return {'FINISHED'}


classes = (
    MODEL_SPLITTER_OT_apply_build,
    MODEL_SPLITTER_OT_cancel_draft,
    MODEL_SPLITTER_OT_update_draft_preview,
    MODEL_SPLITTER_OT_snap_manual_pins,
    MODEL_SPLITTER_OT_reset_pin_positions,
    MODEL_SPLITTER_OT_reset_explode,
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
