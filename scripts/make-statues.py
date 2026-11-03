# Build the 3D arena's statues (web/assets/arena/statues/*.glb) from Rapture Chess's champion avatars, in Blender:
#   blender -b --factory-startup -P scripts/make-statues.py -- ../rapture-chess/public/models/avatars \
#     web/assets/arena/statues 0.12 vaelmyra halvorne tharnyx korvazh nyxarion golvexis pyravane serrivane
# Each avatar's pose is baked (armature applied, rig dropped), its meshes are decimated to the ratio, and it exports as a
# plain GLB (no Draco), so the arena worker reads it with no decoder. web/assets/arena/statues.json places them.
import os
import sys
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
src, out, ratio, names = argv[0], argv[1], float(argv[2]), argv[3:]
os.makedirs(out, exist_ok=True)

export_props = {p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}


def export(path):
    opts = dict(filepath=path, export_format="GLB", use_selection=False, export_apply=True, export_yup=True)
    for k, v in (("export_draco_mesh_compression_enable", False), ("export_animations", False), ("export_cameras", False),
                 ("export_lights", False), ("export_texcoords", False), ("export_tangents", False), ("export_skins", False)):
        if k in export_props:
            opts[k] = v
    bpy.ops.export_scene.gltf(**opts)


for name in names:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(src, f"{name}.glb"))
    before = after = 0
    # statues never move: bake each mesh's pose (apply its armature), then drop the rig, so they export as static meshes
    for ob in [o for o in bpy.context.scene.objects if o.type == "MESH"]:
        bpy.context.view_layer.objects.active = ob
        for m in [m for m in ob.modifiers if m.type == "ARMATURE"]:
            bpy.ops.object.modifier_apply(modifier=m.name)
        ob.parent_type = "OBJECT"
        mw = ob.matrix_world.copy()
        ob.parent = None
        ob.matrix_world = mw
        for vg in list(ob.vertex_groups):
            ob.vertex_groups.remove(vg)
    for ob in [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]:
        bpy.data.objects.remove(ob, do_unlink=True)
    for ob in [o for o in bpy.context.scene.objects if o.type == "MESH"]:
        before += len(ob.data.polygons)
        mod = ob.modifiers.new("decimate", "DECIMATE")
        mod.ratio = ratio
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.modifier_apply(modifier=mod.name)
        after += len(ob.data.polygons)
    path = os.path.join(out, f"{name}.glb")
    export(path)
    print(f"STATUE {name}: {before} -> {after} faces, {os.path.getsize(path) // 1024} KB")
