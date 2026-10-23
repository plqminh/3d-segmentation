"""
ModelSplitter - 3D Print Bed Operators
Provides viewport build volume toggle and automated part shelf-packing onto the print bed.
"""

import bpy
from ..core.print_bed_manager import update_print_bed_visualizer, pack_parts_on_bed, PRINT_BED_OBJ_NAME


class MODEL_SPLITTER_OT_toggle_print_bed(bpy.types.Operator):
    """Toggle 3D Print Bed volume wireframe in the 3D Viewport"""
    bl_idname = "modelsplitter.toggle_print_bed"
    bl_label = "View Print Bed"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.model_splitter
        settings.print_bed.show_bed = not settings.print_bed.show_bed
        update_print_bed_visualizer(context)
        status = "Visible" if settings.print_bed.show_bed else "Hidden"
        self.report({'INFO'}, f"Print Bed Volume: {status}")
        return {'FINISHED'}


class MODEL_SPLITTER_OT_update_print_bed(bpy.types.Operator):
    """Update 3D Print Bed volume dimensions"""
    bl_idname = "modelsplitter.update_print_bed"
    bl_label = "Update Print Bed"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        update_print_bed_visualizer(context)
        return {'FINISHED'}


class MODEL_SPLITTER_OT_pack_print_bed(bpy.types.Operator):
    """Automatically arrange/pack parts on the 3D print bed at Z = 0"""
    bl_idname = "modelsplitter.pack_print_bed"
    bl_label = "Pack on Print Bed"
    bl_description = "Arranges separated parts side-by-side on the print bed with spacing margin"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' and o.name != PRINT_BED_OBJ_NAME for o in bpy.data.objects)

    def execute(self, context):
        settings = context.scene.model_splitter
        bed_props = settings.print_bed

        # Ensure bed visualizer is turned on so user can see it
        if not bed_props.show_bed:
            bed_props.show_bed = True
            update_print_bed_visualizer(context)

        # Target objects: multiple selected mesh objects or all meshes in scene
        selected = [o for o in context.selected_objects if o.type == 'MESH' and o.name != PRINT_BED_OBJ_NAME]
        if len(selected) >= 2:
            targets = selected
        else:
            targets = [o for o in context.scene.objects if o.type == 'MESH' and o.name != PRINT_BED_OBJ_NAME]

        count, out_of_bounds = pack_parts_on_bed(context, targets, margin_mm=bed_props.part_spacing_mm)

        if count == 0:
            self.report({'WARNING'}, "No parts found to pack.")
            return {'CANCELLED'}

        if out_of_bounds > 0:
            self.report({'WARNING'}, f"Packed {count} parts. Caution: {out_of_bounds} parts exceed print bed borders!")
        else:
            self.report({'INFO'}, f"Successfully packed {count} parts cleanly inside the print bed!")

        return {'FINISHED'}


classes = (
    MODEL_SPLITTER_OT_toggle_print_bed,
    MODEL_SPLITTER_OT_update_print_bed,
    MODEL_SPLITTER_OT_pack_print_bed,
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
