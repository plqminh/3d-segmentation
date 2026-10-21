"""
ModelSplitter - Interactive Viewport Cut Line Drawing System
Provides modal drawing in the 3D Viewport with GPU HUD overlay, click-and-drag view-aligned
straight cuts, curved gesture cuts, and surface-locked 3D polygon contours.
"""

import importlib
import math
import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Quaternion
from bpy_extras import view3d_utils

from ..core import cutter_geometry, connectors, boolean_ops, draft_manager
importlib.reload(cutter_geometry)
importlib.reload(connectors)
importlib.reload(boolean_ops)
importlib.reload(draft_manager)

from ..core.cutter_geometry import (
    create_cutter_from_screen_line,
    create_cutter_from_screen_curve,
    create_cutter_from_surface_points,
    resample_smooth_curve_2d,
    resample_closed_curve_3d,
)
from ..core.draft_manager import enter_draft_mode, apply_draft_build


NAVIGATION_EVENTS = {
    'MIDDLEMOUSE',
    'WHEELUPMOUSE',
    'WHEELDOWNMOUSE',
    'WHEELINMOUSE',
    'WHEELOUTMOUSE',
    'TRACKPADPAN',
    'TRACKPADZOOM',
    'MOUSEROTATE',
    'NDOF_MOTION',
    'NUMPAD_0',
    'NUMPAD_1',
    'NUMPAD_2',
    'NUMPAD_3',
    'NUMPAD_4',
    'NUMPAD_5',
    'NUMPAD_6',
    'NUMPAD_7',
    'NUMPAD_8',
    'NUMPAD_9',
    'NUMPAD_PERIOD',
    'NUMPAD_SLASH',
    'NUMPAD_PLUS',
    'NUMPAD_MINUS',
}


class MODEL_SPLITTER_OT_draw_cut_line(bpy.types.Operator):
    bl_idname = "modelsplitter.draw_cut_line"
    bl_label = "Draw Cut Line"
    bl_description = "Interactively draw cutting lines or surface contours across the 3D model"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        settings = getattr(context.scene, "model_splitter", None)
        in_draft = settings.cut.is_in_draft if settings else False
        return obj is not None and obj.type == 'MESH' and not in_draft

    def invoke(self, context, event):
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "View3D not found")
            return {'CANCELLED'}

        self.source_obj = context.active_object
        settings = context.scene.model_splitter
        self.mode = settings.cut.draw_mode

        self.points_2d = []
        self.points_3d = []
        self.points_local = []
        self.mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        self.press_pos = self.mouse_pos.copy()
        self.is_dragging = False
        self.is_rotating_model = False
        self.rot_prev_mouse = self.mouse_pos.copy()
        self.hover_close = False

        # Add 2D GPU draw callback in pixel space
        args = (self, context)
        self.draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_callback_2d, args, 'WINDOW', 'POST_PIXEL'
        )

        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def raycast_surface_point(self, context, x, y):
        """Raycasts from mouse screen coordinates onto the active source mesh."""
        region = context.region
        rv3d = context.region_data
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, (x, y))
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, (x, y))

        depsgraph = context.evaluated_depsgraph_get()
        success, location, normal, index, hit_obj, matrix = context.scene.ray_cast(
            depsgraph, origin, direction
        )

        if success and hit_obj == self.source_obj:
            return location
        return None

    def get_current_2d_points(self, context):
        """
        Returns the 2D screen coordinates for the active stroke.
        In MANUAL mode, dynamically re-projects the 3D surface-locked points so they
        rotate in real time when the user orbits the view or rotates the model.
        """
        if self.mode != 'MANUAL':
            return self.points_2d

        region = context.region
        rv3d = context.region_data
        if not region or not rv3d or not self.source_obj:
            return self.points_2d

        projected = []
        mat_w = self.source_obj.matrix_world
        for pt_local in self.points_local:
            pt_world = mat_w @ pt_local
            p2d = view3d_utils.location_3d_to_region_2d(region, rv3d, pt_world)
            if p2d is not None:
                projected.append(Vector((p2d.x, p2d.y)))
        return projected

    def rotate_view_turntable(self, context, dx_pixels, dy_pixels):
        """Smoothly orbits the 3D Viewport camera around the model."""
        rv3d = context.region_data
        if not rv3d:
            return
        sens = 0.0075
        yaw_quat = Quaternion(Vector((0.0, 0.0, 1.0)), -dx_pixels * sens)
        view_right = rv3d.view_rotation @ Vector((1.0, 0.0, 0.0))
        pitch_quat = Quaternion(view_right, -dy_pixels * sens)
        rv3d.view_rotation = (yaw_quat @ pitch_quat @ rv3d.view_rotation).normalized()

    def modal(self, context, event):
        context.area.tag_redraw()

        # Allow all standard Blender viewport navigation (MMB, wheel, trackpad, Numpad views)
        if event.type in NAVIGATION_EVENTS:
            return {'PASS_THROUGH'}

        # Support Alt+LMB viewport orbiting (for 3-button mouse emulation / tablet users)
        if event.type == 'LEFTMOUSE' and event.alt:
            return {'PASS_THROUGH'}

        # Track mouse coordinates
        if event.type == 'MOUSEMOVE':
            self.mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))

            # Interactive turntable rotation when dragging in empty space or holding R
            if self.is_rotating_model:
                delta = self.mouse_pos - self.rot_prev_mouse
                self.rot_prev_mouse = self.mouse_pos.copy()
                self.rotate_view_turntable(context, delta.x, delta.y)
                return {'RUNNING_MODAL'}

            # Check hover over start point to close loop in Manual mode using live 3D->2D projection
            active_2d = self.get_current_2d_points(context)
            if len(active_2d) >= 3 and self.mode == 'MANUAL':
                dist = (self.mouse_pos - active_2d[0]).length
                self.hover_close = (dist < 22.0)
            else:
                self.hover_close = False

            # Drag sampling for continuous gestures
            if self.is_dragging and self.mode in {'STRAIGHT', 'CURVED'}:
                if self.mode == 'CURVED' and self.points_2d:
                    last_pt = self.points_2d[-1]
                    if (self.mouse_pos - last_pt).length > 6.0:
                        self.points_2d.append(self.mouse_pos.copy())
            elif self.is_dragging and self.mode == 'MANUAL' and event.shift:
                # Shift+Drag in Manual mode paints surface points continuously along the mesh
                hit_3d = self.raycast_surface_point(context, self.mouse_pos.x, self.mouse_pos.y)
                if hit_3d is not None:
                    pt_local = self.source_obj.matrix_world.inverted() @ hit_3d
                    if not self.points_local or (pt_local - self.points_local[-1]).length > 0.02:
                        self.points_local.append(pt_local)
                        self.points_3d.append(hit_3d)
                        self.points_2d.append(self.mouse_pos.copy())
            return {'RUNNING_MODAL'}

        # Left Mouse Button actions
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                curr_pos = Vector((event.mouse_region_x, event.mouse_region_y))
                self.press_pos = curr_pos.copy()

                # Stop R-key rotation mode on click
                if self.is_rotating_model:
                    self.is_rotating_model = False
                    return {'RUNNING_MODAL'}

                # Check if closing loop in Manual mode
                if self.hover_close:
                    return self.confirm_cut(context)

                if self.mode == 'MANUAL':
                    hit_3d = self.raycast_surface_point(context, curr_pos.x, curr_pos.y)
                    if hit_3d is not None:
                        pt_local = self.source_obj.matrix_world.inverted() @ hit_3d
                        self.points_local.append(pt_local)
                        self.points_3d.append(hit_3d)
                        self.points_2d.append(curr_pos)
                        self.is_dragging = True
                    else:
                        # Clicking & dragging on empty space in Manual mode orbits around the model!
                        self.is_rotating_model = True
                        self.rot_prev_mouse = curr_pos.copy()
                else:
                    # STRAIGHT or CURVED screen-space modes
                    if not self.points_2d or (curr_pos - self.points_2d[-1]).length > 2.0:
                        self.points_2d.append(curr_pos)
                    self.is_dragging = True

            elif event.value == 'RELEASE':
                self.is_dragging = False
                if self.is_rotating_model:
                    self.is_rotating_model = False
                    return {'RUNNING_MODAL'}

                end_pt = Vector((event.mouse_region_x, event.mouse_region_y))
                drag_dist = (end_pt - self.press_pos).length

                # Straight cut drag release: if 2 distinct endpoints exist, commit
                if self.mode == 'STRAIGHT' and len(self.points_2d) >= 1:
                    start_pt = self.points_2d[0]
                    if (end_pt - start_pt).length > 25.0:
                        self.points_2d = [start_pt, end_pt]
                        return self.confirm_cut(context)

                # Curved cut drag release: capture final release point; commit immediately if dragged
                elif self.mode == 'CURVED':
                    if self.points_2d and (end_pt - self.points_2d[-1]).length > 2.0:
                        self.points_2d.append(end_pt)
                    if drag_dist > 25.0 and len(self.points_2d) >= 3:
                        return self.confirm_cut(context)

            return {'RUNNING_MODAL'}

        # Keyboard actions
        if event.value == 'PRESS':
            # R key toggles interactive turntable rotation; Arrow keys rotate in 15° steps
            if event.type == 'R':
                self.is_rotating_model = not self.is_rotating_model
                self.rot_prev_mouse = self.mouse_pos.copy()
                return {'RUNNING_MODAL'}
            if event.type == 'LEFT_ARROW':
                self.rotate_view_turntable(context, -35.0, 0.0)
                return {'RUNNING_MODAL'}
            if event.type == 'RIGHT_ARROW':
                self.rotate_view_turntable(context, 35.0, 0.0)
                return {'RUNNING_MODAL'}
            if event.type == 'UP_ARROW':
                self.rotate_view_turntable(context, 0.0, -35.0)
                return {'RUNNING_MODAL'}
            if event.type == 'DOWN_ARROW':
                self.rotate_view_turntable(context, 0.0, 35.0)
                return {'RUNNING_MODAL'}

            # Undo last point: Backspace or Ctrl+Z
            if event.type == 'BACKSPACE' or (event.type == 'Z' and event.ctrl):
                if self.points_2d:
                    self.points_2d.pop()
                if self.points_3d:
                    self.points_3d.pop()
                if self.points_local:
                    self.points_local.pop()
                return {'RUNNING_MODAL'}

            # Confirm cut: Enter or Space
            if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'}:
                return self.confirm_cut(context)

            # Cancel drawing: Esc or Right Click
            if event.type in {'ESC', 'RIGHTMOUSE'}:
                self.cleanup_gpu(context)
                self.report({'INFO'}, "Cut line drawing cancelled")
                return {'CANCELLED'}

        elif event.value == 'RELEASE' and event.type == 'R':
            self.is_rotating_model = False
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    def confirm_cut(self, context):
        """Constructs cutter volume from drawn points and triggers Draft or Easy cut."""
        self.cleanup_gpu(context)

        if self.mode == 'MANUAL':
            if len(self.points_local) < 2 and len(self.points_2d) < 2:
                self.report({'WARNING'}, "Place at least 2 points on the mesh surface to form a cut.")
                return {'CANCELLED'}
        elif len(self.points_2d) < 2:
            self.report({'WARNING'}, "Not enough points drawn to form a cut.")
            return {'CANCELLED'}

        region = context.region
        rv3d = context.region_data
        settings = context.scene.model_splitter
        workflow_mode = settings.cut.workflow_mode

        cutter_obj = None

        if self.mode == 'STRAIGHT':
            p1 = self.points_2d[0]
            p2 = self.points_2d[-1]
            cutter_obj, _, _, _, _ = create_cutter_from_screen_line(
                context, self.source_obj, p1, p2, region, rv3d
            )
        elif self.mode == 'CURVED':
            cutter_obj, _, _, _ = create_cutter_from_screen_curve(
                context, self.source_obj, self.points_2d, region, rv3d
            )
        elif self.mode == 'MANUAL':
            mat_w = self.source_obj.matrix_world
            pts_3d = [mat_w @ pt_l for pt_l in self.points_local]
            view_normal = rv3d.view_rotation @ Vector((0, 0, -1)) if rv3d else Vector((0, -1, 0))
            if len(pts_3d) < 2 and len(self.points_2d) >= 2:
                pts_3d = [
                    view3d_utils.region_2d_to_origin_3d(region, rv3d, p) + view_normal * 1.0
                    for p in self.points_2d
                ]
            try:
                cutter_obj, _, _, _ = cutter_geometry.create_cutter_from_surface_points(
                    context, self.source_obj, pts_3d, view_normal=view_normal
                )
            except TypeError:
                importlib.reload(cutter_geometry)
                cutter_obj, _, _, _ = cutter_geometry.create_cutter_from_surface_points(
                    context, self.source_obj, pts_3d
                )

        if not cutter_obj:
            self.report({'ERROR'}, "Failed to generate cutter geometry from drawn line.")
            return {'CANCELLED'}

        if workflow_mode == 'EASY':
            # Easy mode: Setup and apply immediately
            enter_draft_mode(
                context,
                self.source_obj,
                cut_type=self.mode,
                existing_cutter=cutter_obj,
            )
            results = apply_draft_build(context)
            if results:
                self.report({'INFO'}, f"Cleanly cut model along drawn line into {len(results)} parts with pins!")
            return {'FINISHED'}
        else:
            # Draft mode: Place cutter and preview pins at drawn position
            enter_draft_mode(
                context,
                self.source_obj,
                cut_type=self.mode,
                existing_cutter=cutter_obj,
            )
            self.report({'INFO'}, "Draft Cut initialized from drawn line! Adjust pins or click 'Apply Cut (Build)'")
            return {'FINISHED'}

    def cleanup_gpu(self, context):
        if getattr(self, 'draw_handler', None):
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self.draw_handler, 'WINDOW')
            except Exception:
                pass
            self.draw_handler = None
        if context and getattr(context, 'area', None):
            context.area.tag_redraw()

    def draw_callback_2d(self, op, context):
        """Draws real-time line, smoothed spline preview, points, rubber-band, and HUD on 3D Viewport."""
        # Top HUD Banner
        font_id = 0
        blf.size(font_id, 14)

        mode_names = {
            'STRAIGHT': "Straight (Click & Drag or Click 2 Points)",
            'CURVED': "Curved (Drag arc or Click points + Enter)",
            'MANUAL': "Manual Surface (Click on mesh | Drag empty space / MMB / R to Rotate)",
        }
        mode_text = mode_names.get(self.mode, self.mode)

        hud_title = f"ModelSplitter | DRAW CUT LINE  [{mode_text}]"
        if self.mode == 'MANUAL':
            hud_help = "LMB on Mesh: Add Point  |  LMB Empty/MMB/R/Arrows: Rotate View  |  Ctrl+Z: Undo  |  Enter/Click Start: Confirm"
        else:
            hud_help = "LMB: Draw/Add Point  |  MMB/R/Arrows: Orbit View  |  Ctrl+Z: Undo  |  Enter: Confirm Cut  |  Esc: Cancel"

        # Banner background
        w = context.region.width
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')

        banner_bg_coords = [
            (0, context.region.height),
            (w, context.region.height),
            (w, context.region.height - 48),
            (0, context.region.height - 48),
        ]
        batch_bg = batch_for_shader(shader, 'TRI_FAN', {"pos": banner_bg_coords})
        shader.bind()
        shader.uniform_float("color", (0.05, 0.08, 0.12, 0.85))
        batch_bg.draw(shader)

        # Draw HUD text
        blf.position(font_id, 20, context.region.height - 22, 0)
        blf.color(font_id, 0.2, 0.9, 1.0, 1.0)
        blf.draw(font_id, hud_title)

        blf.position(font_id, 20, context.region.height - 40, 0)
        blf.color(font_id, 0.85, 0.85, 0.85, 0.9)
        blf.draw(font_id, hud_help)

        active_pts = self.get_current_2d_points(context)

        # Draw connecting line strip or smoothed Catmull-Rom curve
        if len(active_pts) >= 2:
            if self.mode == 'CURVED':
                settings = getattr(context.scene, "model_splitter", None)
                num_s = getattr(settings.cut, "editable_points", 24) if settings else 24
                preview_pts = list(active_pts)
                if not self.is_dragging and (self.mouse_pos - preview_pts[-1]).length > 4.0:
                    preview_pts.append(self.mouse_pos)
                smooth_pts = resample_smooth_curve_2d(preview_pts, num_samples=max(32, num_s * 2))
                line_coords = [(p.x, p.y) for p in smooth_pts]
            elif self.mode == 'MANUAL' and len(active_pts) >= 3:
                if self.hover_close:
                    pts_3d_preview = [Vector((p.x, p.y, 0.0)) for p in active_pts]
                    closed_pts = resample_closed_curve_3d(pts_3d_preview, num_samples=48, smooth_passes=2)
                    line_coords = [(p.x, p.y) for p in closed_pts] + [(closed_pts[0].x, closed_pts[0].y)]
                else:
                    smooth_pts = resample_smooth_curve_2d(active_pts, num_samples=max(24, len(active_pts) * 6))
                    line_coords = [(p.x, p.y) for p in smooth_pts]
            else:
                line_coords = [(p.x, p.y) for p in active_pts]

            batch_line = batch_for_shader(shader, 'LINE_STRIP', {"pos": line_coords})
            shader.bind()
            gpu.state.line_width_set(3.0)
            shader.uniform_float("color", (1.0, 0.25, 0.2, 0.95))  # Bright red cut path
            batch_line.draw(shader)

        # Draw rubber-band line from last point to mouse
        if active_pts and not self.is_rotating_model and (self.mode != 'CURVED' or len(active_pts) == 1):
            last = active_pts[-1]
            rubber_coords = [(last.x, last.y), (self.mouse_pos.x, self.mouse_pos.y)]
            batch_rubber = batch_for_shader(shader, 'LINES', {"pos": rubber_coords})
            shader.bind()
            gpu.state.line_width_set(2.0)
            shader.uniform_float("color", (1.0, 0.85, 0.2, 0.8))
            batch_rubber.draw(shader)

        # Draw control point dots
        if active_pts:
            # First point indicator (Green anchor to close)
            first_p = active_pts[0]
            box_size = 14.0 if not self.hover_close else 20.0
            hs = box_size * 0.5
            start_box = [
                (first_p.x - hs, first_p.y - hs),
                (first_p.x + hs, first_p.y - hs),
                (first_p.x + hs, first_p.y + hs),
                (first_p.x - hs, first_p.y + hs),
            ]
            batch_start = batch_for_shader(shader, 'TRI_FAN', {"pos": start_box})
            shader.bind()
            shader.uniform_float("color", (0.1, 1.0, 0.3, 0.95))
            batch_start.draw(shader)

            # Other point dots
            if len(active_pts) > 1:
                point_coords = [(p.x, p.y) for p in active_pts[1:]]
                batch_pts = batch_for_shader(shader, 'POINTS', {"pos": point_coords})
                shader.bind()
                gpu.state.point_size_set(7.0)
                shader.uniform_float("color", (1.0, 1.0, 1.0, 0.9))
                batch_pts.draw(shader)


class MODEL_SPLITTER_OT_swap_pin(bpy.types.Operator):
    bl_idname = "modelsplitter.swap_pin"
    bl_label = "Swap Pin Side"
    bl_description = "Toggles male pin placement between Part A and Part B"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ..core.draft_manager import swap_pin_target
        swap_pin_target(context)
        self.report({'INFO'}, "Swapped male pin target side")
        return {'FINISHED'}


classes = (
    MODEL_SPLITTER_OT_draw_cut_line,
    MODEL_SPLITTER_OT_swap_pin,
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
