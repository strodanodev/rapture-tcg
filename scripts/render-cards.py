# Rapture TCG: illustrations for the cards that have no NFT painting (spells, relics, the Construct token), rendered in
# Blender so they sit beside the collection's own 3D renders. Each card gets a small lit scene for what it does (a
# lightning bolt, a quake, a blade, a crystal, a shield, a fan of cards, a helm), in its element's colour, with glare.
#   blender -b --factory-startup --python scripts/render-cards.py -- web/data/game.json web/assets/cards [--only lava-burst]
# Writes <card id>.<VERSION>.webp and art.json (card id -> file), which the client reads. The deploy caches assets for
# a year, so bump VERSION on every re-render. Stone textures are Rapture Chess's CC0 Poly Haven sets, read from
# ../rapture-chess/scripts/textures beside this game in the theforge monorepo (standing alone, put them there or
# change TEX below).
import bpy, bmesh, json, math, os, random, sys

_args = sys.argv[sys.argv.index("--") + 1:]
game_path, out_dir = _args[:2]
ONLY = _args[_args.index("--only") + 1] if "--only" in _args else None
VERSION = 1
W, H = 800, 584   # the card's art window is about 1.37:1
TEX = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "rapture-chess", "scripts", "textures"))
ELEMENT = {   # glow colour, dim colour for the backdrop
    "lava": ((1.0, 0.32, 0.08), (0.05, 0.012, 0.008)),
    "water": ((0.2, 0.75, 1.0), (0.008, 0.025, 0.05)),
    "earth": ((0.35, 1.0, 0.45), (0.01, 0.035, 0.015)),
    "metal": ((0.78, 0.7, 1.0), (0.025, 0.022, 0.04)),
    "neutral": ((1.0, 0.78, 0.38), (0.04, 0.03, 0.015)),
}


# ---------------------------------------------------------------------------- materials
def principled(m):
    return next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def emis(name, color, strength, lit=True):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = principled(m)
    p.inputs["Base Color"].default_value = (*color, 1) if lit else (0, 0, 0, 1)
    p.inputs["Emission Color"].default_value = (*color, 1)
    p.inputs["Emission Strength"].default_value = strength
    return m


def metal(name, color, rough=0.3):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = principled(m)
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Metallic"].default_value = 1.0
    p.inputs["Roughness"].default_value = rough
    return m


def glass(name, color, glow):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = principled(m)
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = 0.05
    p.inputs["Coat Weight"].default_value = 1.0
    p.inputs["Emission Color"].default_value = (*color, 1)
    p.inputs["Emission Strength"].default_value = glow
    return m


def stone(name, tid, tint=(1, 1, 1), scale=1.5):
    """A Poly Haven set, box-projected in object space (no UVs needed)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = principled(m)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (scale, scale, scale)
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])

    def img(kind, data):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(os.path.join(TEX, tid, f"{kind}_512.jpg"), check_existing=True)
        if data:
            n.image.colorspace_settings.name = "Non-Color"
        n.projection = "BOX"
        n.projection_blend = 0.3
        nt.links.new(mapping.outputs["Vector"], n.inputs["Vector"])
        return n

    d = img("diff", False)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    nt.links.new(d.outputs["Color"], mix.inputs["A"])
    mix.inputs["B"].default_value = (*tint, 1)
    nt.links.new(mix.outputs["Result"], p.inputs["Base Color"])
    a = img("arm", True)
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(a.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], p.inputs["Roughness"])
    nm = img("nor_gl", True)
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nm.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], p.inputs["Normal"])
    return m


# ---------------------------------------------------------------------------- geometry
def obj(name, me, mat=None, loc=(0, 0, 0), rot=(0, 0, 0), smooth_shade=False):
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    if mat:
        me.materials.append(mat)
    o.location, o.rotation_euler = loc, rot
    if smooth_shade:
        for p in me.polygons:
            p.use_smooth = True
    return o


def prism(name, outline, depth, mat, loc=(0, 0, 0), rot=(0, 0, 0)):
    """Extrude a 2D outline (x, z points) by `depth` along y, centred."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, -depth / 2, z)) for x, z in outline]
    f = bm.faces.new(vs)
    r = bmesh.ops.extrude_face_region(bm, geom=[f])
    bmesh.ops.translate(bm, verts=[v for v in r["geom"] if isinstance(v, bmesh.types.BMVert)], vec=(0, depth, 0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return obj(name, me, mat, loc, rot)


def prim(kind, name, mat, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), **kw):
    getattr(bpy.ops.mesh, f"primitive_{kind}_add")(location=loc, rotation=rot, **kw)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    if mat:
        o.data.materials.append(mat)
    return o


def backdrop(color):
    """A far wall that glows softly behind the emblem: emission fading radially to nothing (no hard edge)."""
    m = bpy.data.materials.new("backdrop")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type == "BSDF_PRINCIPLED":
            nt.nodes.remove(n)
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (2.4, 3.6, 2.4)   # plane coords are +-0.5: this reaches 0 near the edges
    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "SPHERICAL"
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "POWER"
    mul.inputs[1].default_value = 2.2
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], grad.inputs["Vector"])
    nt.links.new(grad.outputs["Fac"], mul.inputs[0])
    strength = nt.nodes.new("ShaderNodeMath")
    strength.operation = "MULTIPLY"
    strength.inputs[1].default_value = 0.7
    nt.links.new(mul.outputs[0], strength.inputs[0])
    nt.links.new(strength.outputs[0], em.inputs["Strength"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    wall = prim("plane", "Backdrop", m, loc=(0, 6.0, 2.0), rot=(math.radians(90), 0, 0), size=1)
    wall.scale = (16, 9, 1)
    return wall


def bevel(o, w, seg=2):
    b = o.modifiers.new("bevel", "BEVEL")
    b.width, b.segments = w, seg
    return o


def rough_up(o, strength, size, levels=2):
    s = o.modifiers.new("sub", "SUBSURF")
    s.levels = s.render_levels = levels
    t = bpy.data.textures.new(o.name + "_n", "VORONOI")
    t.noise_scale = size
    d = o.modifiers.new("disp", "DISPLACE")
    d.texture, d.strength, d.texture_coords = t, strength, "GLOBAL"
    return o


def crystal(name, h, w, mat, loc, rot=(0, 0, 0)):
    bm = bmesh.new()
    top, bot = bm.verts.new((0, 0, h * 0.5)), bm.verts.new((0, 0, -h * 0.5))
    ring = [bm.verts.new((w * math.cos(i * math.tau / 6), w * math.sin(i * math.tau / 6), 0)) for i in range(6)]
    for i in range(6):
        j = (i + 1) % 6
        bm.faces.new((ring[i], ring[j], top))
        bm.faces.new((ring[j], ring[i], bot))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return obj(name, me, mat, loc, rot)


def sparks(color, n=46, seed=1, spread=2.4, z0=0.3, z1=3.0):
    r = random.Random(seed)
    m = emis("spark", color, 8, lit=False)
    for i in range(n):
        s = r.uniform(0.008, 0.024)
        prim("ico_sphere", f"spark{i}", m, loc=(r.uniform(-spread, spread), r.uniform(-1.2, 1.6), r.uniform(z0, z1)), scale=(s, s, s), subdivisions=1)


def pedestal():
    p = prim("cylinder", "Pedestal", stone("ped", "medieval_blocks_05", (0.55, 0.52, 0.5), 2.0), loc=(0, 0, 0.3), vertices=8, radius=0.75, depth=0.6)
    bevel(p, 0.04)
    q = prim("cylinder", "PedestalTop", stone("ped2", "medieval_blocks_05", (0.6, 0.57, 0.55), 2.0), loc=(0, 0, 0.66), vertices=8, radius=0.6, depth=0.12)
    bevel(q, 0.03)
    return 0.72


# ---------------------------------------------------------------------------- emblems (one per effect)
def bolt(c, base, amount=2):
    """One bolt for light damage, two for 3-4, three for 5 or more."""
    outline = [(0.25, 1.4), (-0.35, 0.15), (0.0, 0.15), (-0.3, -1.1), (0.45, 0.35), (0.08, 0.35), (0.4, 1.4)]
    n = 1 if amount <= 2 else 2 if amount <= 4 else 3
    for k in range(n):
        x = (k - (n - 1) / 2) * 0.85
        b = prism(f"Bolt{k}", outline, 0.14, emis("bolt", c, 18), loc=(x, 0.3 * abs(x), base + 1.25 - 0.15 * abs(x)), rot=(0, math.radians(-8 + 10 * x), 0))
        bevel(b, 0.03)
    ring = prim("torus", "Impact", emis("impact", c, 10), loc=(0.1, 0, base + 0.03), major_radius=0.55, minor_radius=0.025)
    ring.scale = (1, 1, 0.3)


def quake(c, base):
    rock = stone("rock", "rock_face_03", (0.45, 0.42, 0.42), 1.2)
    for i in range(9):
        a = i * math.tau / 9 + 0.2
        r = random.Random(i)
        f = prim("cube", f"Fissure{i}", emis("fissure", c, 14), loc=(math.cos(a) * 0.9, math.sin(a) * 0.9 + 0.3, base + 0.01), rot=(0, 0, a), scale=(0.9, 0.02, 0.01))
        chunk = prim("ico_sphere", f"Chunk{i}", rock, loc=(math.cos(a) * r.uniform(0.6, 1.6), math.sin(a) * 0.4 + 0.2, base + r.uniform(0.3, 1.8)),
                     rot=(r.uniform(0, 3), r.uniform(0, 3), r.uniform(0, 3)), scale=[r.uniform(0.12, 0.3)] * 3, subdivisions=2)
        rough_up(chunk, 0.12, 0.3, 1)
    core = prim("uv_sphere", "Core", emis("core", c, 22), loc=(0, 0.3, base + 0.05), scale=(0.35, 0.35, 0.08))


def buff(c, base):
    steel = metal("steel", (0.85, 0.82, 0.78), 0.18)
    gold = metal("gold", (1.0, 0.72, 0.3), 0.25)
    blade = prism("Blade", [(-0.11, 0), (0.11, 0), (0.11, 1.7), (0, 2.0), (-0.11, 1.7)], 0.05, steel, loc=(0, 0, base + 0.75))
    bevel(blade, 0.02)
    prim("cube", "Guard", gold, loc=(0, 0, base + 0.72), scale=(0.42, 0.06, 0.06))
    prim("cylinder", "Grip", metal("leather", (0.15, 0.08, 0.05), 0.6), loc=(0, 0, base + 0.42), radius=0.05, depth=0.55)
    prim("uv_sphere", "Pommel", gold, loc=(0, 0, base + 0.13), radius=0.08)
    for k, z in enumerate((0.9, 1.5, 2.1)):
        t = prim("torus", f"Aura{k}", emis("aura", c, 12 - k * 3), loc=(0, 0, base + z), major_radius=0.55 - k * 0.1, minor_radius=0.018)
        t.rotation_euler = (math.radians(12), 0, 0)   # lying round the blade, not across it


def energy(c, base):
    crystal("Crystal", 1.5, 0.38, glass("cr", c, 1.6), (0, 0, base + 1.25), (0, 0, 0.3))
    for k, tilt in enumerate((65, 110)):
        t = prim("torus", f"Orbit{k}", emis("orbit", c, 10), loc=(0, 0, base + 1.25), major_radius=0.85, minor_radius=0.015)
        t.rotation_euler = (math.radians(tilt), math.radians(20 * (k * 2 - 1)), 0)


def shield(c, base):
    outline = [(-0.75, 0.9), (0.75, 0.9), (0.75, 0.1), (0.5, -0.5), (0, -0.9), (-0.5, -0.5), (-0.75, 0.1)]
    s = prism("Shield", outline, 0.16, stone("sh", "castle_wall_slates", (0.7, 0.72, 0.7), 1.8), loc=(0, 0, base + 1.3))
    bevel(s, 0.05, 3)
    rim_pts = [(x * 1.08, z * 1.08) for x, z in outline]
    r = prism("Rim", rim_pts, 0.1, emis("rim", c, 12), loc=(0, 0.04, base + 1.3))
    prim("uv_sphere", "Boss", metal("boss", (0.9, 0.85, 0.75), 0.25), loc=(0, -0.12, base + 1.38), radius=0.2, scale=(1, 0.5, 1))


def draw(c, base):
    face = emis("cardface", c, 1.4, lit=False)
    for k, a in enumerate((-22, 0, 22)):
        card = prim("cube", f"Card{k}", metal("cardback", (0.08, 0.07, 0.1), 0.4), loc=(0, 0.02 * k, base + 1.2), scale=(0.42, 0.02, 0.6))
        card.rotation_euler = (0, math.radians(a), 0)
        card.location.x = math.sin(math.radians(a)) * 0.9
        card.location.z = base + 1.15 + math.cos(math.radians(a)) * 0.2
        bevel(card, 0.02)
        glow = prim("cube", f"Glow{k}", face, loc=card.location, scale=(0.36, 0.021, 0.54))
        glow.rotation_euler = card.rotation_euler
        glow.location.y -= 0.005


def helm(c, base, x=0.0, s=1.0):
    bronze = metal("bronze", (0.75, 0.5, 0.28), 0.32)
    head = prim("uv_sphere", "Helm", bronze, loc=(x, 0, base + 1.25 * s), radius=0.62 * s, scale=(1, 0.95, 1.1))
    prim("cube", "Visor", emis("visor", c, 16), loc=(x, -0.58 * s, base + 1.3 * s), scale=(0.42 * s, 0.05 * s, 0.07 * s))
    prim("cube", "Crest", bronze, loc=(x, 0, base + 1.95 * s), scale=(0.04 * s, 0.5 * s, 0.18 * s))
    prim("cylinder", "Neck", bronze, loc=(x, 0, base + 0.55 * s), radius=0.35 * s, depth=0.3 * s)


def idol(c, base):
    body = prim("cylinder", "Idol", stone("idol", "rock_wall_08", (0.35, 0.3, 0.3), 2.0), loc=(0, 0, base + 0.75), vertices=6, radius=0.38, depth=1.5)
    bevel(body, 0.05)
    prim("uv_sphere", "Eye", emis("eye", c, 25), loc=(0, -0.33, base + 1.1), radius=0.1, scale=(1, 0.5, 0.6))
    for k in range(4):
        prim("cube", f"Crack{k}", emis("crack", c, 10), loc=(0, -0.37, base + 0.35 + k * 0.18), rot=(0, math.radians(20 - 13 * k), 0), scale=(0.18, 0.01, 0.012))


def summon(c, base):
    helm(c, base, x=-0.62, s=0.72)
    helm(c, base, x=0.62, s=0.72)


EMBLEM = {"bolt": bolt, "quake": quake, "buff": buff, "energy": energy, "shield": shield, "draw": draw, "unit": helm, "idol": idol, "summon": summon}


def key_for(card):
    op, target = (card.get("effect") or {}).get("op"), str((card.get("effect") or {}).get("target", ""))
    if card["type"] == "unit":
        return "unit"
    if op == "summon":
        return "summon"
    if op == "damage":
        return "idol" if card["type"] == "relic" else ("quake" if target.startswith("all") else "bolt")
    return op if op in EMBLEM else "energy"


# ---------------------------------------------------------------------------- the stage
def scene_for(card):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    glow, dim = ELEMENT.get(card.get("element") or "neutral", ELEMENT["neutral"])
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.image_settings.file_format = "WEBP"
    sc.render.image_settings.quality = 82
    sc.render.film_transparent = False
    if hasattr(sc.eevee, "use_raytracing"):
        sc.eevee.use_raytracing = True
    sc.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs[0].default_value = (*dim, 1)

    # ground: dark stone under everything, fading into the dark
    ground = prim("plane", "Ground", stone("ground", "rock_face_03", (0.3, 0.28, 0.28), 1.0), size=14)
    # a backdrop glow behind the emblem
    backdrop(glow)
    base = pedestal() if card["type"] == "relic" else 0.0
    key = key_for(card)
    if key == "bolt":
        bolt(glow, base, (card.get("effect") or {}).get("amount", 2))
    else:
        EMBLEM[key](glow, base)
    sparks(glow, seed=len(card["id"]))

    # lights: a warm key from the front left, the element's colour as rims behind, and a glow at the emblem
    def light(name, kind, energy, color, loc, rot=(0, 0, 0), size=1.0):
        l = bpy.data.lights.new(name, kind)
        l.energy, l.color = energy, color
        if kind == "AREA":
            l.size = size
        o = bpy.data.objects.new(name, l)
        bpy.context.collection.objects.link(o)
        o.location, o.rotation_euler = loc, rot
        return o
    light("Key", "AREA", 300, (1.0, 0.93, 0.85), (-3.2, -4.0, 4.2), (math.radians(50), 0, math.radians(-38)), 3.0)
    light("RimL", "AREA", 380, glow, (-3.0, 2.6, 2.6), (math.radians(-60), 0, math.radians(-130)), 2.0)
    light("RimR", "AREA", 380, glow, (3.0, 2.6, 2.6), (math.radians(-60), 0, math.radians(130)), 2.0)
    light("Core", "POINT", 140, glow, (0, -0.6, base + 1.2))

    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    bpy.context.collection.objects.link(cam)
    cam.data.lens = 42
    cam.location = (0, -6.4, base + 1.55)
    cam.rotation_euler = (math.radians(86), 0, 0)
    sc.camera = cam

    # glare: the hot parts bloom
    try:
        ng = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
        sc.compositing_node_group = ng
        rl = ng.nodes.new("CompositorNodeRLayers")
        g = ng.nodes.new("CompositorNodeGlare")
        # a soft bloom, not star streaks (Type is a menu socket in Blender 5; its item names vary by version)
        for v in ("Bloom", "BLOOM", "Fog Glow", "FOG_GLOW"):
            try:
                g.inputs["Type"].default_value = v
                break
            except Exception:
                pass
        for name, v in (("Threshold", 1.6), ("Size", 0.7), ("Strength", 0.55)):
            if name in g.inputs:
                g.inputs[name].default_value = v
        out = ng.nodes.new("NodeGroupOutput")
        ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        ng.links.new(rl.outputs["Image"], g.inputs["Image"])
        ng.links.new(g.outputs["Image"], out.inputs[0])
    except Exception as e:   # glare is a finish, not a requirement
        print("GLARE skipped:", e)


game = json.load(open(game_path, encoding="utf8"))
cards = [c for c in game["cards"] if not c.get("token")]
os.makedirs(out_dir, exist_ok=True)
manifest_path = os.path.join(out_dir, "art.json")
manifest = json.load(open(manifest_path, encoding="utf8")) if os.path.exists(manifest_path) else {}
for card in cards:
    if ONLY and card["id"] != ONLY:
        continue
    scene_for(card)
    file = f"{card['id']}.{VERSION}.webp"
    bpy.context.scene.render.filepath = os.path.abspath(os.path.join(out_dir, file))
    bpy.ops.render.render(write_still=True)
    manifest[card["id"]] = file
    print("CARD", card["id"], key_for(card), os.path.getsize(os.path.join(out_dir, file)))
with open(manifest_path, "w", encoding="utf8") as f:
    json.dump(dict(sorted(manifest.items())), f, indent=2)
    f.write("\n")
