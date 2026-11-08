# Rapture TCG: the two arenas behind the battle, built parametrically in Blender and exported as GLBs. Forked from
# Rapture Chess's scripts/build-arenas.py: the same halls, with the placeholder props sculpted (subdivided, displaced
# by world-space noise, decimated) and textured, and exported without Draco (the arena worker has no decoder).
#   blender -b --factory-startup --python scripts/build-arenas.py -- web/assets/arena renders --no-render [--only valhalla]
# Files are written as <realm>.<VERSION>.glb, and web/assets/arena/arena.json names them: the deploy caches assets for
# a year, so a rebuilt arena needs a new file name. Bump VERSION on every rebuild.
# Textures: the CC0 Poly Haven sets in the Rapture Chess repo's scripts/textures (see its README.txt for the source
# URLs), read from ../rapture-chess beside this game in the theforge monorepo. Standing alone, put that folder there or
# change TEX below.
# Valhalla: a round hall of carved stone pillars and arches on flagstones, banners, braziers, a rune circle round
#   a polished dais (the game draws its mirror there).
# Underworld: a basalt crater on burned ground, obsidian spires, a lava moat with bridges, bone totems, stalactites
#   and ember crystals.
# Stone, ground and rock are CC0 Poly Haven sets (scripts/textures, 1k: diffuse, OpenGL normal, AO/rough/metal),
# UV-mapped by world-space box projection so the tiling stays even across pieces. Before export every mesh is merged
# by material: a handful of draw calls per arena, which is what keeps phones at 60 fps.
import bpy, bmesh, math, sys, os, random

_args = sys.argv[sys.argv.index("--") + 1:]
out_dir, render_dir = _args[:2]
DO_RENDER = "--no-render" not in _args
RES = 512
VERSION = 8
# the CC0 Poly Haven sets are Rapture Chess's (see its scripts/textures/README.txt); this script shares them
TEX = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "rapture-chess", "scripts", "textures"))


def reset():
    if bpy.app.background:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        return
    # a live Blender (MCP): factory settings would unload the addon serving this call, so empty the file instead
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.cameras, bpy.data.lights):
        for item in list(coll):
            coll.remove(item)


def mat(name, base, metallic=0.0, rough=0.6, emis=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    n = next(x for x in m.node_tree.nodes if x.type == "BSDF_PRINCIPLED")
    n.inputs["Base Color"].default_value = (*base, 1.0)
    n.inputs["Metallic"].default_value = metallic
    n.inputs["Roughness"].default_value = rough
    if emis:
        n.inputs["Emission Color"].default_value = (*emis, 1.0)
        n.inputs["Emission Strength"].default_value = strength
    return m


def tex_mat(name, tid, normal=1.0):
    """A PBR material from a Poly Haven set, wired the way the glTF exporter reads it (base colour, normal map, and the
    ARM image's G/B channels as roughness/metalness)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(x for x in nt.nodes if x.type == "BSDF_PRINCIPLED")

    def img(kind, data):
        # 512 px copies (made from the 1k sources with Pillow): plenty for walls seen from the board, and the exporter
        # embeds the file bytes as they are, so this is what keeps each GLB phone-sized
        im = bpy.data.images.load(os.path.join(TEX, tid, f"{kind}_{RES}.jpg"), check_existing=True)
        if data:
            im.colorspace_settings.name = "Non-Color"
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = im
        return n

    d = img("diff", False)
    nt.links.new(d.outputs["Color"], bsdf.inputs["Base Color"])
    a = img("arm", True)
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(a.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    nm = img("nor_gl", True)
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nmap.inputs["Strength"].default_value = normal
    nt.links.new(nm.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    m["tile"] = 1.0
    return m


def uv_box(o, size):
    """World-space box projection: each face takes the two axes its normal is not facing, divided by `size` metres."""
    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uv = bm.loops.layers.uv.verify()
    mw = o.matrix_world
    rot = mw.to_3x3()
    for f in bm.faces:
        n = rot @ f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        u, v = [(1, 2), (0, 2), (0, 1)][ax]
        for l in f.loops:
            w = mw @ l.vert.co
            l[uv].uv = (w[u] / size, w[v] / size)
    bm.to_mesh(me)
    bm.free()


TILE = {}   # material name -> texture tile size (m); objects with a textured material get box UVs at export


def link(o, parent=None):
    bpy.context.collection.objects.link(o)
    if parent:
        o.parent = parent
    return o


def smooth(o, angle=40):
    for p in o.data.polygons:
        p.use_smooth = True
    if hasattr(o.data, "set_sharp_from_angle"):
        o.data.set_sharp_from_angle(angle=math.radians(angle))


def bevel(o, width, segments=2):
    b = o.modifiers.new("bevel", "BEVEL")
    b.width = width
    b.segments = segments
    b.limit_method = "ANGLE"
    b.angle_limit = math.radians(40)


def spin(name, profile, material, segments=24, loc=(0, 0, 0), rot=0, parent=None, bev=0.0):
    bm = bmesh.new()
    verts = [bm.verts.new((r, 0, z)) for r, z in profile]
    edges = [bm.edges.new((verts[i], verts[i + 1])) for i in range(len(verts) - 1)]
    bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(0, 0, 1), angle=math.tau, steps=segments, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(material)
    o = link(bpy.data.objects.new(name, me), parent)
    o.location = loc
    o.rotation_euler = (0, 0, rot)
    smooth(o)
    if bev:
        bevel(o, bev)
    return o


def box(name, size, loc, material, rot=(0, 0, 0), parent=None, bev=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    o.name = name
    o.data.name = name
    o.data.materials.append(material)
    if parent:
        o.parent = parent
    if bev:
        bevel(o, bev)
        smooth(o)
    return o


def ring_floor(name, outer, inner, z, depth, material, parent, bev=0.0, sides=4, rot=0.0):
    bm = bmesh.new()
    vo = [bm.verts.new((outer * math.cos(rot + i * math.tau / sides), outer * math.sin(rot + i * math.tau / sides), z)) for i in range(sides)]
    vi = [bm.verts.new((inner * math.cos(rot + i * math.tau / sides), inner * math.sin(rot + i * math.tau / sides), z)) for i in range(sides)]
    for i in range(sides):
        bm.faces.new((vo[i], vo[(i + 1) % sides], vi[(i + 1) % sides], vi[i]))
    r = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    bmesh.ops.translate(bm, verts=[v for v in r["geom"] if isinstance(v, bmesh.types.BMVert)], vec=(0, 0, -depth))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(material)
    o = link(bpy.data.objects.new(name, me), parent)
    if bev:
        bevel(o, bev)
        smooth(o)
    return o


def sculpt(o, strength, size, levels=2, kind="VORONOI", keep=None):
    """Carve a primitive into something hand-made: subdivide it, push it out along its normals by world-space noise
    (Voronoi for fractured rock and glass, Clouds for worn bone and stone), then decimate to `keep` of the faces."""
    sub = o.modifiers.new("subdivide", "SUBSURF")
    sub.subdivision_type = "SIMPLE"
    sub.levels = sub.render_levels = levels
    tex = bpy.data.textures.new(f"{o.name}_noise", kind)
    tex.noise_scale = size
    if kind == "CLOUDS":
        tex.noise_depth = 3
    d = o.modifiers.new("displace", "DISPLACE")
    d.texture = tex
    d.texture_coords = "GLOBAL"
    d.strength = strength
    if keep:
        dec = o.modifiers.new("decimate", "DECIMATE")
        dec.ratio = keep
    return o


def shard(name, h, w, material, loc, rot, parent):
    """A crystal: a six-sided prism with a pointed tip and a short root, facets kept sharp."""
    bm = bmesh.new()
    top, bot = bm.verts.new((0, 0, h)), bm.verts.new((0, 0, -h * 0.12))
    lo = [bm.verts.new((w * math.cos(i * math.tau / 6), w * math.sin(i * math.tau / 6), 0.0)) for i in range(6)]
    hi = [bm.verts.new((w * 0.85 * math.cos(i * math.tau / 6), w * 0.85 * math.sin(i * math.tau / 6), h * 0.7)) for i in range(6)]
    for i in range(6):
        j = (i + 1) % 6
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
        bm.faces.new((hi[i], hi[j], top))
        bm.faces.new((lo[j], lo[i], bot))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(material)
    o = link(bpy.data.objects.new(name, me), parent)
    o.location = loc
    o.rotation_euler = rot
    return o


def finish():
    """Apply modifiers, give textured objects box UVs, then merge every mesh by material (one draw call each)."""
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    for o in meshes:
        mn = o.data.materials[0].name if o.data.materials else ""
        if mn in TILE:
            uv_box(o, TILE[mn])
    groups = {}
    for o in meshes:
        groups.setdefault(o.data.materials[0].name if o.data.materials else "", []).append(o)
    for mn, objs in groups.items():
        bpy.ops.object.select_all(action="DESELECT")
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        if len(objs) > 1:
            bpy.ops.object.join()
        bpy.context.view_layer.objects.active.name = f"M_{mn}"
    for o in list(bpy.data.objects):
        if o.type == "EMPTY":
            bpy.data.objects.remove(o)


def export(name):
    finish()
    bpy.ops.object.select_all(action="SELECT")
    path = os.path.join(out_dir, f"{name}.{VERSION}.glb")
    kw = dict(filepath=path, export_format="GLB", export_apply=True, export_yup=True, export_animations=False, use_selection=True,
              export_image_format="JPEG", export_jpeg_quality=78)
    # no Draco: the game's arena worker reads plain glTF with no decoder or WebAssembly
    bpy.ops.export_scene.gltf(**kw)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    print("EXPORT", name, os.path.getsize(path), "meshes", len(meshes), "faces", sum(len(o.data.polygons) for o in meshes))


def render(name, cam_loc, cam_rot, bg):
    if not DO_RENDER:
        return
    scene = bpy.context.scene
    cam = link(bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")))
    cam.location = cam_loc
    cam.rotation_euler = cam_rot
    cam.data.lens = 28
    scene.camera = cam
    sun = link(bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN")))
    sun.data.energy = 2.5
    sun.rotation_euler = (math.radians(55), math.radians(10), math.radians(-30))
    w = scene.world or bpy.data.worlds.new("World")
    scene.world = w
    w.use_nodes = True
    n = next(x for x in w.node_tree.nodes if x.type == "BACKGROUND")
    n.inputs[0].default_value = (*bg, 1)
    engines = [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    scene.render.engine = next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH") if e in engines)
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.filepath = os.path.abspath(os.path.join(render_dir, f"{name}.png"))
    bpy.ops.render.render(write_still=True)
    print("RENDER", name)


# ============================================================================ VALHALLA
def valhalla():
    reset()
    random.seed(7)
    TILE.clear()
    STONE = tex_mat("vh_stone", "castle_wall_slates"); TILE["vh_stone"] = 2.6
    FLOOR = tex_mat("vh_floor", "monastery_stone_floor"); TILE["vh_floor"] = 3.2
    BLOCKS = tex_mat("vh_blocks", "medieval_blocks_05"); TILE["vh_blocks"] = 2.4
    PILLAR = tex_mat("vh_pillar", "rock_face_03"); TILE["vh_pillar"] = 3.4   # hewn rock: slate brick read as chimney stacks
    DARK = mat("vh_dark", (0.16, 0.14, 0.13), 0.1, 0.7)
    GOLD = mat("rapture_gold", (1.0, 0.72, 0.28), 1.0, 0.3)
    FIRE = mat("vh_fire", (0.1, 0.05, 0.02), 0.0, 0.8, (1.0, 0.55, 0.15), 6.0)
    RUNE = mat("vh_rune", (0.05, 0.05, 0.08), 0.0, 0.6, (0.55, 0.8, 1.0), 3.0)
    BANNER = mat("vh_banner", (0.05, 0.12, 0.28), 0.0, 0.85)
    root = link(bpy.data.objects.new("Valhalla", None))

    # the hall floor: flagstones from the dais (radius 9, the game's polished mirror) out to the walkway, gold trim
    # and a glowing rune circle on the dais edge, then flagstone ground far beyond the pillars
    ring_floor("Floor", 17.0, 9.0, -0.17, 0.5, FLOOR, root, sides=32)
    ring_floor("DaisTrim", 9.3, 8.95, -0.12, 0.1, GOLD, root, sides=48)
    ring_floor("RuneCircle", 8.75, 8.6, -0.155, 0.01, RUNE, root, sides=48)
    ring_floor("FloorRing", 5.3, 4.75, -0.12, 0.1, GOLD, root, sides=8, rot=math.pi / 8)
    ring_floor("Walk", 18.5, 16.6, 0.25, 0.6, BLOCKS, root, bev=0.03, sides=32)
    ring_floor("Ground", 60.0, 18.4, -0.3, 0.3, FLOOR, root, sides=24)
    # two steps up to the walkway
    ring_floor("Step", 16.8, 16.2, 0.0, 0.3, BLOCKS, root, bev=0.02, sides=32)

    # pillars on the ring, carved (a fluted profile) with gold caps and rune bands
    n = 16
    for i in range(n):
        a = i * math.tau / n + math.pi / 16
        x, y = 15.2 * math.cos(a), 15.2 * math.sin(a)
        prof = [(0, 0), (0.75, 0), (0.75, 0.25), (0.55, 0.3), (0.55, 6.6), (0.7, 6.8), (0.7, 7.1), (0.85, 7.2), (0.85, 7.5), (0, 7.5)]
        spin(f"Pillar_{i}", prof, PILLAR, segments=16, loc=(x, y, 0.2), rot=a, parent=root, bev=0.02)
        spin(f"PillarCap_{i}", [(0.5, 6.55), (0.72, 6.55), (0.72, 6.65), (0.5, 6.65)], GOLD, segments=12, loc=(x, y, 0.2), parent=root)
        # a gold band, not a glowing one: lit pale blue, the bands read as unlit plastic tape
        spin(f"PillarRune_{i}", [(0.56, 3.0), (0.58, 3.0), (0.58, 3.25), (0.56, 3.25)], GOLD, segments=12, loc=(x, y, 0.2), parent=root)
        if i % 2 == 0:
            # a war banner on every other pillar, facing the board, with a gold rod and hem
            bx, by = 14.45 * math.cos(a), 14.45 * math.sin(a)
            box(f"Banner_{i}", (0.06, 1.1, 3.0), (bx, by, 4.6), BANNER, rot=(0, 0, a), parent=root)
            box(f"BannerRod_{i}", (0.08, 1.4, 0.08), (bx, by, 6.15), GOLD, rot=(0, 0, a), parent=root)
            box(f"BannerHem_{i}", (0.07, 1.1, 0.12), (bx - 0.01 * math.cos(a), by - 0.01 * math.sin(a), 3.15), GOLD, rot=(0, 0, a), parent=root)
            box(f"BannerSigil_{i}", (0.07, 0.42, 0.42), (bx - 0.02 * math.cos(a), by - 0.02 * math.sin(a), 4.9), GOLD, rot=(math.pi / 4, 0, a), parent=root)   # embroidered gold
    # arches between pillars: a lintel ring high up, and a second ring of taller pillars further out
    # 48 sides: at 16 the ring read as a faceted plank from the low title camera
    ring_floor("Lintel", 16.0, 14.4, 7.9, 0.5, BLOCKS, root, bev=0.03, sides=48, rot=math.pi / 16)
    ring_floor("LintelGold", 15.3, 15.1, 7.95, 0.08, GOLD, root, sides=48, rot=math.pi / 16)
    for i in range(8):
        a = i * math.tau / 8
        x, y = 24.0 * math.cos(a), 24.0 * math.sin(a)
        spin(f"Outer_{i}", [(0, 0), (1.2, 0), (1.2, 0.3), (0.9, 0.4), (0.9, 11.0), (1.1, 11.3), (1.1, 11.8), (0, 11.8)], STONE, segments=10, loc=(x, y, -0.5), parent=root, bev=0.03)
        spin(f"OuterFire_{i}", [(0, 11.8), (0.5, 11.85), (0.35, 12.4), (0.12, 12.8), (0, 12.85)], FIRE, segments=8, loc=(x, y, -0.5), parent=root)
    # braziers at the four board corners: a bowl on a tripod with an emissive fire core
    for (sx, sy) in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
        x, y = sx * 6.6, sy * 6.6
        # on the floor (its top is at -0.17): at 0 they floated above it
        spin("Brazier", [(0, 0), (0.45, 0), (0.45, 0.08), (0.12, 0.12), (0.12, 1.1), (0.55, 1.25), (0.62, 1.55), (0.5, 1.6), (0.45, 1.35), (0, 1.3)], DARK, segments=16, loc=(x, y, -0.17), parent=root, bev=0.01)
        spin("BrazierFire", [(0, 1.3), (0.4, 1.32), (0.3, 1.7), (0.12, 2.0), (0, 2.05)], FIRE, segments=10, loc=(x, y, -0.17), parent=root)
    # (no roof beams: with nothing above them they floated, and spoked behind the logo on phones)
    # fallen blocks and standing runestones around the floor for scale
    for i in range(10):
        a = random.uniform(0, math.tau)
        r = random.uniform(10.5, 13.5)
        sculpt(box(f"Block_{i}", (random.uniform(0.6, 1.4), random.uniform(0.6, 1.0), random.uniform(0.4, 0.9)), (r * math.cos(a), r * math.sin(a), 0.5), BLOCKS, rot=(0, 0, a), parent=root), 0.12, 0.4, levels=3, kind="VORONOI", keep=0.4)
    for i in range(6):
        a = i * math.tau / 6 + 0.3
        # broad face to the hall (side-on, a stone read as a thin grey box with a glowing edge), a rune carved in it:
        # a stem and two branches, glowing, just proud of the face
        face = a + math.pi / 2
        sculpt(box(f"Runestone_{i}", (0.9, 0.3, 2.6), (12.5 * math.cos(a), 12.5 * math.sin(a), 1.13), STONE, rot=(0, 0, face), parent=root), 0.06, 0.3, levels=3, kind="CLOUDS", keep=0.45)
        gx, gy = 12.33 * math.cos(a), 12.33 * math.sin(a)
        box(f"RuneStem_{i}", (0.07, 0.03, 1.3), (gx, gy, 1.55), RUNE, rot=(0, 0, face), parent=root)
        for k, (dz, tilt) in enumerate(((0.35, 0.75), (0.0, 0.75))):
            ox = 0.14 * math.cos(face)
            oy = 0.14 * math.sin(face)
            box(f"RuneBranch_{i}_{k}", (0.36, 0.03, 0.06), (gx + ox, gy + oy, 1.55 + dz), RUNE, rot=(0, -tilt, face), parent=root)
    export("valhalla")
    render("valhalla", (3, -17, 15), (math.radians(50), 0, math.radians(10)), (0.06, 0.07, 0.1))


# ============================================================================ UNDERWORLD
def underworld():
    reset()
    random.seed(13)
    TILE.clear()
    BASALT = tex_mat("uw_basalt", "rock_wall_08"); TILE["uw_basalt"] = 3.0
    ROCK = tex_mat("uw_rock", "rock_face_03"); TILE["uw_rock"] = 4.0
    ASH = tex_mat("uw_ash", "burned_ground_01"); TILE["uw_ash"] = 4.5
    OBSIDIAN = mat("uw_obsidian", (0.03, 0.02, 0.04), 0.4, 0.25)
    LAVA = mat("uw_lava", (0.2, 0.05, 0.0), 0.0, 0.9, (1.0, 0.3, 0.05), 5.0)
    BONE = mat("uw_bone", (0.78, 0.72, 0.6), 0.0, 0.7)
    EMBER = mat("uw_ember", (0.05, 0.02, 0.01), 0.0, 0.9, (1.0, 0.45, 0.1), 4.0)
    CRYSTAL = mat("uw_crystal", (0.12, 0.02, 0.05), 0.2, 0.2, (1.0, 0.18, 0.12), 3.0)
    root = link(bpy.data.objects.new("Underworld", None))

    # crater floor: basalt plates round the board, a lava moat, a broken basalt field, then burned ground to the horizon
    ring_floor("Plate", 6.4, 4.95, -0.17, 0.6, BASALT, root, bev=0.04, sides=32)
    ring_floor("PlateRim", 5.15, 4.95, -0.12, 0.1, BONE, root, sides=32)
    ring_floor("Lava", 9.0, 6.3, -0.45, 0.2, LAVA, root, sides=32)
    ring_floor("Field", 22.0, 8.8, -0.3, 0.7, ROCK, root, bev=0.05, sides=24)
    ring_floor("Ground", 60.0, 21.5, -0.55, 0.3, ASH, root, sides=24)
    # four bridges over the moat, bone-edged
    for i in range(4):
        a = i * math.tau / 4 + math.pi / 4
        # carved basalt, not glossy obsidian: from the title camera a smooth slab read as a white plank
        # a thick bevelled slab, broken by Voronoi like the basalt plates, with squat stone posts at its corners in
        # place of thin rails (from the title camera, rails read as planks)
        sculpt(box(f"Bridge_{i}", (3.4, 1.6, 0.42), (7.6 * math.cos(a), 7.6 * math.sin(a), -0.28), BASALT, rot=(0, 0, a), parent=root, bev=0.12), 0.14, 0.45, levels=2, kind="VORONOI", keep=0.6)
        for s in (-1, 1):
            for t in (-1, 1):
                px = 7.6 * math.cos(a) + t * 1.45 * math.cos(a) - s * 0.72 * math.sin(a)
                py = 7.6 * math.sin(a) + t * 1.45 * math.sin(a) + s * 0.72 * math.cos(a)
                post = spin(f"BridgePost_{i}{s}{t}", [(0, 0), (0.24, 0), (0.2, 0.42), (0.26, 0.5), (0.14, 0.62), (0, 0.66)], BASALT, segments=8, loc=(px, py, -0.1), rot=a, parent=root)
                sculpt(post, 0.05, 0.2, levels=1, kind="VORONOI")
    # obsidian spires: tall jagged cones in a ring, leaning outward (their old ember bands read as tape, and are gone)
    for i in range(14):
        a = i * math.tau / 14 + random.uniform(-0.12, 0.12)
        r = random.uniform(16.0, 20.0)
        h = random.uniform(7.0, 15.0)
        x, y = r * math.cos(a), r * math.sin(a)
        prof = [(0, 0), (1.6, 0), (1.3, h * 0.25), (0.9, h * 0.5), (0.5, h * 0.78), (0.12, h), (0, h)]
        o = spin(f"Spire_{i}", prof, OBSIDIAN, segments=14, loc=(x, y, -0.6), rot=a, parent=root)
        # fractured volcanic glass: finer, shallower Voronoi facets, kept sharp-edged (deep ones read as lumps)
        sculpt(o, 0.32, 0.8, levels=2, kind="VORONOI", keep=0.7)
        o.rotation_euler = (math.radians(random.uniform(-8, 8)), math.radians(random.uniform(4, 14)), a)
        # broken-off shards round its foot, leaning out, so each spire stands in its own rubble
        for k in range(random.randint(2, 3)):
            ba = a + random.uniform(-1.2, 1.2)
            bh = random.uniform(1.2, 2.8)
            shard(f"SpireShard_{i}_{k}", bh, bh * 0.3, OBSIDIAN, (x + 1.9 * math.cos(ba), y + 1.9 * math.sin(ba), -0.4),
                  (math.radians(random.uniform(-30, 30)), math.radians(random.uniform(-30, 30)), ba), root)
    # bone tusks and boulders near the board: great curved tusks breaking out of the ash, leaning in toward the dais
    # (stacked-sphere totems read as toys)
    for i in range(8):
        a = i * math.tau / 8 + 0.2
        h = 2.6 + (i % 3) * 0.6
        t = spin(f"Tusk_{i}", [(0, 0), (0.42, 0), (0.38, h * 0.25), (0.3, h * 0.5), (0.2, h * 0.75), (0.08, h * 0.95), (0, h)], BONE, segments=12, loc=(11.5 * math.cos(a), 11.5 * math.sin(a), -0.55), rot=a, parent=root)
        # a curve: bend the tusk toward the dais, more toward its tip
        for v in t.data.vertices:
            k = max(0.0, v.co.z / h) ** 2
            v.co.x -= 0.9 * k
        t.rotation_euler = (0, math.radians(-12 - (i % 2) * 8), a + math.pi)
        sculpt(t, 0.04, 0.2, levels=1, kind="CLOUDS")
    for i in range(12):
        a = random.uniform(0, math.tau)
        r = random.uniform(10.5, 15.0)
        s = random.uniform(0.5, 1.2)
        b = spin(f"Boulder_{i}", [(0, 0), (s, 0), (s * 0.9, s * 0.6), (s * 0.5, s * 1.1), (0, s * 1.2)], BASALT, segments=8, loc=(r * math.cos(a), r * math.sin(a), 0.1), rot=a, parent=root)
        sculpt(b, s * 0.45, s * 0.7, levels=2, kind="VORONOI", keep=0.6)
    # ember crystals breaking through the field in clusters
    for c in range(9):
        a = c * math.tau / 9 + random.uniform(-0.2, 0.2)
        r = random.uniform(10.0, 14.5)
        cx, cy = r * math.cos(a), r * math.sin(a)
        for k in range(random.randint(3, 5)):
            h = random.uniform(0.7, 2.2)
            shard(f"Crystal_{c}_{k}", h, h * 0.18, CRYSTAL, (cx + random.uniform(-0.6, 0.6), cy + random.uniform(-0.6, 0.6), 0.0),
                  (math.radians(random.uniform(-25, 25)), math.radians(random.uniform(-25, 25)), random.uniform(0, math.tau)), root)
    # lava fissures: jagged glowing cracks branching across the field, so the floor itself is lit from below
    fr = random.Random(41)
    for c in range(16):
        a = c * math.tau / 16 + fr.uniform(-0.15, 0.15)
        r0 = fr.uniform(9.2, 10.5)
        x, y, heading = r0 * math.cos(a), r0 * math.sin(a), a + fr.uniform(-0.4, 0.4)
        for k in range(fr.randint(4, 7)):
            seg = fr.uniform(1.0, 2.2)
            heading += fr.uniform(-0.6, 0.6)
            nx, ny = x + seg * math.cos(heading), y + seg * math.sin(heading)
            box(f"Fissure_{c}_{k}", (seg + 0.12, fr.uniform(0.1, 0.22), 0.04), ((x + nx) / 2, (y + ny) / 2, -0.285), LAVA, rot=(0, 0, heading), parent=root)
            x, y = nx, ny
            if math.hypot(x, y) > 21.0:
                break
    # a cracked dome of ribs overhead
    for i in range(12):
        a = i * math.tau / 12
        sculpt(box(f"Rib_{i}", (14.0, 0.5, 0.8), (11.0 * math.cos(a), 11.0 * math.sin(a), 13.5), BASALT, rot=(0, math.radians(-22), a), parent=root), 0.3, 0.9, levels=2, kind="VORONOI", keep=0.5)
    # (no stalactites: from the low title camera they hung from open sky)
    export("underworld")
    render("underworld", (3, -17, 15), (math.radians(50), 0, math.radians(10)), (0.04, 0.01, 0.01))


os.makedirs(out_dir, exist_ok=True)
os.makedirs(render_dir, exist_ok=True)
if "--only" in _args:
    {"valhalla": valhalla, "underworld": underworld}[_args[_args.index("--only") + 1]]()
else:
    valhalla()
    underworld()
