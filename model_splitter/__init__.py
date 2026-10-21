"""
ModelSplitter - Blender Extension
A precision model splitting and alignment keying add-on for 3D printing.
"""

bl_info = {
    "name": "ModelSplitter",
    "author": "User",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > ModelSplitter",
    "description": "Split 3D models into printable parts with automatic pin/socket connectors",
    "category": "Mesh",
}

import importlib
import bpy

# Handle reload of all utility, core, operator, and UI submodules in dependency order
if "properties" in locals():
    from .utils import math_utils, mesh_utils
    from .core import cutter_geometry, connectors, boolean_ops, draft_manager, mesh_check
    importlib.reload(math_utils)
    importlib.reload(mesh_utils)
    importlib.reload(cutter_geometry)
    importlib.reload(connectors)
    importlib.reload(boolean_ops)
    importlib.reload(draft_manager)
    importlib.reload(mesh_check)
    importlib.reload(properties)
    importlib.reload(draw_cut_ops)
    importlib.reload(straight_cut)
    importlib.reload(draft_ops)
    importlib.reload(mesh_check_ops)
    importlib.reload(export_ops)
    importlib.reload(panels)

from .utils import math_utils, mesh_utils
from .core import cutter_geometry, connectors, boolean_ops, draft_manager, mesh_check
from . import properties
from .operators import draw_cut_ops, straight_cut, draft_ops, mesh_check_ops, export_ops
from .ui import panels


modules = (
    properties,
    draw_cut_ops,
    straight_cut,
    draft_ops,
    mesh_check_ops,
    export_ops,
    panels,
)


def register():
    for mod in modules:
        mod.register()


def unregister():
    for mod in reversed(modules):
        mod.unregister()


if __name__ == "__main__":
    register()
