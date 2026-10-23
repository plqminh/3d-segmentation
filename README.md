# ModelSplitter — Blender 4.2+ / 5.x Add-on

A high-precision, non-destructive 3D model splitting, keying, and print preparation add-on for 3D printing (SLA/FDM), combining the interactive drawing workflows of **CatPin** with the complete prep and segmentation feature set of **TTMinimal Split**.

---

## 🌟 Key Features

### 1. Scale Master & Model Preparation
- **Real-Time Millimeter Dials**: Displays width, depth, and height in millimeters directly converted from scene geometry.
- **Uniform Proportional Scaling**: Set a target maximum dimension (e.g. `200mm`) to automatically scale the model proportionately.
- **One-Click Positioning**:
  - **Focus View (`Reset View`)**: Immediately frames and zooms the viewport camera onto your selected model.
  - **To Origin**: Centers model geometry and places origin at world `(0, 0, 0)`.
  - **Drop to Bed (Z=0)**: Drops the model so its lowest bounding-box contact point sits flush on the print surface.
  - **Quick Rotate**: One-click 90° re-orientation buttons (**Stand Up**, **Lay Flat**, and **Turn 90°**).
  - **Fuse Models (Boolean Union / Join)**: Merges multi-part imports (e.g. limbs, props, accessories) into a single watertight mesh.

### 2. Multi-Mode Cutting Tools
- **Straight View Cut**: Angle your camera, click and drag across the model to slice cleanly along the line-of-sight.
- **Curved Arc Cut**: Draw a gestural curved stroke across the viewport; sweeps into an organic cutting ribbon to hide seam lines.
- **Plane Cut (3D Transform Gizmo)**: Spawns an interactive planar cutter with Blender's standard 3D gizmo for effortless positioning and slicing.
- **Manual Surface Contour**: Click points directly onto the 3D mesh surface to carve around muscle groups and limb joints.
- **Interactive Contour Curve Editing**: In Draft Mode, click **Edit Contour** to adjust control points or press `Ctrl+Click` to insert extra curve points before finalizing.
- **Cutter Mesh Resolution**: Fine-tune the ribbon step resolution (`Cut Smoothness`) for silk-smooth curved seams.

### 3. Intelligent Alignment Connectors (Pins & Sockets)
- **Connector Shapes**:
  - **Cylindrical & Conical (Tapered)**: Standard friction-fit assembly pins.
  - **Neodymium Magnet Slots**: Recessed cylindrical pockets for standard disc magnets (**3x1**, **3x2**, **5x2**, **6x3**, **8x3 mm**).
  - **D-Pin (Anti-Rotation)**: Keyed flat-edge cylinder preventing rotational slippage on circular joints.
  - **Ball Joint**: Articulated spherical male head and clearance socket.
  - **Rectangular Keys & Custom Meshes**: For structural alignment.
- **Auto-Fit Within Mesh (`Tự căn vừa khối`)**: Automatically bounds pin radius and depth inside the cross-section walls, preventing pins from punching through thin exterior geometry (such as necks or fingers).
- **Independent Tolerances & Clearances**: SLA resin (`0.1–0.2mm`) and FDM (`0.2–0.35mm`).
- **Swap Pin Side & Explode Preview**: One-click male pin flipping and live interactive joint inspection slider.

### 4. Mesh Health, Watertight Remesh & Decimation
- **BVH Diagnostics**: Detect non-manifold edges, boundary holes, zero-area faces, and self-intersections with one-click **Auto-Heal**.
- **Watertight Voxel Remesh**: High-speed voxel remeshing with millimeter-based resolution to generate clean manifold topology.
- **Decimate Mesh**: Ratio-based polycount reduction preserving sharp geometry while lightening heavy sculpts.

### 5. 3D Print Bed View & Automated Packing
- **Custom Print Bed Visualizer**: Toggle a 3D wireframe build plate and volume box (`Width x Depth x Height mm`) in the viewport.
- **Pack on Print Bed**: Automated 2D collision-aware shelf-packing arranging all separated cut parts neatly across the print bed at `Z=0` with configurable margin spacing.
- **Batch Export**: Export parts in a single click to **STL** or **OBJ** formats.

### 6. Basic vs. Advanced Mode
- **Basic Mode**: Streamlined, intuitive toolbar for rapid slicing and print packing.
- **Advanced Mode**: Full engineering dials, tolerances, custom clearance gaps, and mesh decimation.

---

## 🚀 Installation

### Option 1: Install from ZIP file
1. In Blender (4.2, 4.5, 5.0, or 5.1+), open **Edit > Preferences > Add-ons**.
2. Click the drop-down menu in the upper-right corner and select **Install from Disk...**
3. Select `model_splitter.zip` located in `e:\3D segmentation\model_splitter.zip`.
4. Enable the **ModelSplitter** extension.

### Option 2: Live Development Symlink
The add-on is already synced to:
`%APPDATA%\Blender Foundation\Blender\5.1\extensions\user_default\model_splitter`

---

## 📖 Recommended Workflow

1. Select your model in Object Mode and open the **ModelSplitter** N-Panel.
2. In **Scale Master**, click **Drop to Bed (Z=0)** and adjust **Target Size (mm)** if needed.
3. Check mesh health under **Mesh Health & Remesh** (or run **Voxel Remesh** if the mesh has open holes).
4. Choose your cutting style (**Straight Cut**, **Curved Cut**, **Plane Cut**, or **Draw Cut Line**).
5. Choose your alignment connector shape (**Cylinder**, **Magnet Slot**, **D-Pin**, or **Ball Joint**).
6. In **Draft Mode**, inspect the seam with **Explode Preview**, then click **Apply Cut (Build)**.
7. Under **Print Bed & Batch Export**, click **View Print Bed**, click **Pack on Bed**, and hit **Export All Parts**.
