#!/usr/bin/env python3
"""VRM -> Roblox R6 custom model pack for the xioma model changer.

Reads a .vrm (glTF binary), extracts the bind-pose skinned mesh, splits it
into R6 body parts (Head, Torso, arms, legs) by bone weights, bakes all
textures into a single atlas, and writes:
  <out>/<name>/<part>.mesh   (Roblox binary mesh v2.00, stud-space coords)
  <out>/<name>/tex.png       (shared texture atlas)
  <out>/<name>/thumb.png     (rendered preview, front/side/back)
  <out>/<name>/entry.json    (models.json entry snippet)
"""
import json
import math
import os
import struct
import sys

import numpy as np
from PIL import Image


COMPONENTS = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
TYPES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def load_glb(path):
    data = open(path, "rb").read()
    magic, version, total = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67, "not a GLB"
    off = 12
    js, bin_chunk = None, b""
    while off < len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        off += 8
        chunk = data[off:off + clen]
        off += clen
        if ctype == 0x4E4F534A:
            js = json.loads(chunk)
        elif ctype == 0x004E4942:
            bin_chunk = chunk
    return js, bin_chunk


def read_accessor(js, bin_chunk, index):
    a = js["accessors"][index]
    assert "sparse" not in a, "sparse accessors not supported"
    bv = js["bufferViews"][a["bufferView"]]
    comp = COMPONENTS[a["componentType"]]
    ncomp = TYPES[a["type"]]
    comp_size = struct.calcsize("<" + comp)
    stride = bv.get("byteStride") or ncomp * comp_size
    base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    count = a["count"]
    dtype = np.dtype(np.float64 if comp == "f" else np.int64).newbyteorder("<")
    if stride == ncomp * comp_size:
        raw = np.frombuffer(bin_chunk, dtype=np.dtype(comp).newbyteorder("<"),
                            count=count * ncomp, offset=base)
        return raw.reshape(count, ncomp).astype(dtype)
    out = np.empty((count, ncomp), dtype=dtype)
    fmt = "<" + comp * ncomp
    for i in range(count):
        out[i] = struct.unpack_from(fmt, bin_chunk, base + i * stride)
    return out


def quat_to_mat(q):
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def node_local_matrix(n):
    if "matrix" in n:
        return np.array(n["matrix"], dtype=np.float64).reshape(4, 4).T
    t = np.array(n.get("translation", [0, 0, 0]), dtype=np.float64)
    r = quat_to_mat(n.get("rotation", [0, 0, 0, 1]))
    s = np.array(n.get("scale", [1, 1, 1]), dtype=np.float64)
    m = np.eye(4)
    m[:3, :3] = r @ np.diag(s)
    m[:3, 3] = t
    return m


def compute_world_matrices(js):
    nodes = js["nodes"]
    world = [np.eye(4) for _ in nodes]
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    order = []
    seen = set()

    def visit(i):
        if i in seen:
            return
        seen.add(i)
        if i in parent:
            visit(parent[i])
        order.append(i)

    for i in range(len(nodes)):
        visit(i)
    for i in order:
        local = node_local_matrix(nodes[i])
        p = parent.get(i)
        world[i] = world[p] @ local if p is not None else local
    return world, parent


def humanoid_map(js, parent):
    ext = js.get("extensions", {})
    node_bone = {}
    if "VRM" in ext:  # VRM 0.x
        for hb in ext["VRM"].get("humanoid", {}).get("humanBones", []):
            node_bone[int(hb["node"])] = hb["bone"]
    elif "VRMCvrm" in ext:  # VRM 1.0
        for bone, info in ext["VRMCvrm"].get("humanoid", {}).get("humanBones", {}).items():
            node_bone[int(info["node"])] = bone
    BONE_PART = {
        "head": "Head", "neck": "Head",
        "hips": "Torso", "spine": "Torso", "chest": "Torso", "upperChest": "Torso",
        "leftShoulder": "Left Arm", "leftUpperArm": "Left Arm",
        "leftLowerArm": "Left Arm", "leftHand": "Left Arm",
        "rightShoulder": "Right Arm", "rightUpperArm": "Right Arm",
        "rightLowerArm": "Right Arm", "rightHand": "Right Arm",
        "leftUpperLeg": "Left Leg", "leftLowerLeg": "Left Leg",
        "leftFoot": "Left Leg", "leftToes": "Left Leg",
        "rightUpperLeg": "Right Leg", "rightLowerLeg": "Right Leg",
        "rightFoot": "Right Leg", "rightToes": "Right Leg",
    }
    resolved = {}

    def resolve(node):
        if node in resolved:
            return resolved[node]
        seen = set()
        cur = node
        while cur is not None and cur not in seen:
            seen.add(cur)
            bone = node_bone.get(cur)
            if bone and bone in BONE_PART:
                resolved[node] = BONE_PART[bone]
                return resolved[node]
            cur = parent.get(cur)
        resolved[node] = None
        return None

    for node in node_bone:
        resolve(node)
    return node_bone, resolve


def bone_world_pos(js, world, node_bone, bone):
    for node, name in node_bone.items():
        if name == bone:
            return world[node][:3, 3].copy()
    return None


def write_mesh(path, verts, faces):
    with open(path, "wb") as fh:
        fh.write(b"version 2.00\n")
        fh.write(struct.pack("<HBBII", 12, 36, 12, len(verts), len(faces)))
        for v in verts:
            fh.write(struct.pack("<9f", v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], 0.0))
        for f in faces:
            fh.write(struct.pack("<III", f[0], f[1], f[2]))


def rot_z(theta):
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)


def pack_atlas(tiles):
    total = sum(im.width * im.height for _, im in tiles)
    side = 256
    while side * side < total * 1.35 and side < 4096:
        side *= 2
    atlas = Image.new("RGBA", (side, side), (255, 255, 255, 255))
    placement = {}
    x = y = row_h = 0
    for key, im in tiles:
        if x + im.width > side:
            x = 0
            y += row_h
            row_h = 0
        if y + im.height > side:
            return None
        atlas.paste(im.convert("RGBA"), (x, y))
        placement[key] = (x, y, im.width, im.height)
        x += im.width
        row_h = max(row_h, im.height)
    return atlas, placement


def build_atlas(js, bin_chunk, mats_used):
    tiles = []
    tile_key = {}
    color_tiles = {}
    for mat_i, (img_i, color) in mats_used.items():
        if img_i is not None:
            key = ("img", img_i)
            if key not in tile_key:
                img_js = js["images"][img_i]
                bv = js["bufferViews"][img_js["bufferView"]]
                blob = bin_chunk[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]
                im = Image.open(__import__("io").BytesIO(blob)).convert("RGBA")
                if im.width > 1024 or im.height > 1024:
                    im = im.resize((im.width // 2, im.height // 2), Image.LANCZOS)
                tile_key[key] = im
            tiles.append((key, tile_key[key]))
        else:
            rgb = tuple(int(c * 255) for c in (list(color) + [1, 1, 1])[:3])
            if rgb not in color_tiles:
                color_tiles[rgb] = Image.new("RGBA", (16, 16), rgb + (255,))
            tiles.append((("color", rgb), color_tiles[rgb]))
    packed = None
    for _ in range(4):
        packed = pack_atlas(tiles)
        if packed:
            break
        for i, (key, im) in enumerate(tiles):
            if im.width > 64:
                tiles[i] = (key, im.resize((max(64, im.width // 2), max(64, im.height // 2)), Image.LANCZOS))
    assert packed, "atlas overflow"
    return packed


def render_thumb(path, tris_per_part, atlas, W, H):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection

    fig, axes = plt.subplots(1, 3, figsize=(7.5, 3), dpi=96)
    light = np.array([0.4, 0.8, 0.45])
    light = light / np.linalg.norm(light)
    arr = np.asarray(atlas.convert("RGB"))
    for ax, label in zip(axes, ["front", "side", "back"]):
        ax.set_axis_off()
        polys, colors = [], []
        for part, (verts, faces) in tris_per_part.items():
            if not len(faces):
                continue
            v = verts
            for f in faces[:: max(1, len(faces) // 6000)]:
                tri = v[[f[0], f[1], f[2]]]
                n = np.cross(tri[1, :3] - tri[0, :3], tri[2, :3] - tri[0, :3])
                nn = np.linalg.norm(n)
                shade = 0.55 + 0.45 * abs(np.dot(n / nn, light)) if nn else 0.7
                uvs = tri[:, 3:5] * np.array([W, H])
                uc = np.clip(uvs.mean(axis=0).astype(int), [0, 0], [W - 1, H - 1])
                col = arr[uc[1], uc[0]] / 255.0
                if label == "front":
                    p = tri[:, [0, 1]] * np.array([1, 1])
                elif label == "back":
                    p = tri[:, [0, 1]] * np.array([-1, 1])
                else:
                    p = tri[:, [2, 1]] * np.array([-1, 1])
                polys.append(p * np.array([1, -1]))
                colors.append(np.clip(np.array(col) * shade, 0, 1))
        if polys:
            pc = PolyCollection(polys, facecolors=colors, edgecolors="none")
            ax.add_collection(pc)
            all_xy = np.concatenate([np.array(p) for p in polys])
            cx, cy = all_xy.mean(axis=0)
            ax.set_xlim(cx - 3.4, cx + 3.4)
            ax.set_ylim(cy - 3.6, cy + 3.6)
            ax.set_aspect("equal")
    fig.savefig(path, transparent=True)
    plt.close(fig)


PARTS = ["Head", "Torso", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
ARM_ANGLE = math.radians(75)


def convert(vrm_path, out_dir, name):
    js, bin_chunk = load_glb(vrm_path)
    world, parent = compute_world_matrices(js)
    node_bone, resolve_part = humanoid_map(js, parent)

    skin = js["skins"][0]
    joints = skin["joints"]
    ibm = read_accessor(js, bin_chunk, skin["inverseBindMatrices"])
    ibm = ibm.astype(np.float32).reshape(-1, 4, 4).transpose(0, 2, 1)
    joint_mats = np.stack([world[j] @ ibm[k] for k, j in enumerate(joints)]).astype(np.float32)

    node_part = {j: resolve_part(j) for j in joints}

    verts_all, norms_all, uvs_all = [], [], []
    part_of_vert = []
    prim_of_vert = []
    tri_records = []
    mats_used = {}
    prim_mat_key = []
    prim_id = 0
    vert_offset = 0

    for node in js["nodes"]:
        if "mesh" not in node:
            continue
        mesh = js["meshes"][node["mesh"]]
        for prim in mesh["primitives"]:
            attrs = prim["attributes"]
            P = read_accessor(js, bin_chunk, attrs["POSITION"])
            N = read_accessor(js, bin_chunk, attrs["NORMAL"]) if "NORMAL" in attrs else np.zeros((len(P), 3))
            UV = read_accessor(js, bin_chunk, attrs["TEXCOORD_0"]) if "TEXCOORD_0" in attrs else np.zeros((len(P), 2))
            idx = read_accessor(js, bin_chunk, prim["indices"]).astype(np.int64).ravel()
            if "JOINTS_0" in attrs and "WEIGHTS_0" in attrs:
                J = read_accessor(js, bin_chunk, attrs["JOINTS_0"]).astype(np.int64)
                Wt = read_accessor(js, bin_chunk, attrs["WEIGHTS_0"])
            else:
                J = np.zeros((len(P), 4), dtype=np.int64)
                Wt = np.zeros((len(P), 4))
                Wt[:, 0] = 1.0

            n_v = len(P)
            pos = np.empty((n_v, 3), np.float64)
            nrm = np.empty((n_v, 3), np.float64)
            Pf, Nf = P.astype(np.float32), N.astype(np.float32)
            CH = 65536
            for s0 in range(0, n_v, CH):
                s1 = min(s0 + CH, n_v)
                Jc, Wc = J[s0:s1], Wt[s0:s1].astype(np.float32)
                M = np.einsum("vkij,vk->vij", joint_mats[Jc], Wc)
                Ph = np.concatenate([Pf[s0:s1], np.ones((s1 - s0, 1), np.float32)], axis=1)
                pos[s0:s1] = np.einsum("vij,vj->vi", M, Ph)[:, :3]
                nrm[s0:s1] = np.einsum("vij,vj->vi", M[:, :3, :3], Nf[s0:s1])
            nn = np.linalg.norm(nrm, axis=1, keepdims=True)
            nrm = nrm / np.maximum(nn, 1e-9)

            dom = np.argmax(Wt, axis=1)
            sel_joints = J[np.arange(len(dom)), dom]
            part = np.array([node_part.get(joints[int(jj)]) or "Torso" for jj in sel_joints])

            mat_i = prim.get("material")
            img_i = None
            color = [1, 1, 1, 1]
            if mat_i is not None:
                mat = js["materials"][mat_i]
                pbr = mat.get("pbrMetallicRoughness", {})
                if "baseColorTexture" in pbr:
                    tex_i = pbr["baseColorTexture"]["index"]
                    img_i = js["textures"][tex_i].get("source")
                color = pbr.get("baseColorFactor", [1, 1, 1, 1])
            mat_key = mat_i if mat_i is not None else -1 - prim_id
            mats_used[mat_key] = (img_i, color)

            base = vert_offset
            vert_offset += len(P)
            verts_all.append(pos)
            norms_all.append(nrm)
            uvs_all.append(UV)
            part_of_vert.append(part)
            prim_of_vert.append(np.full(len(P), prim_id, dtype=np.int64))
            tri_records.append((base + idx[0::3], base + idx[1::3], base + idx[2::3], prim_id))
            prim_mat_key.append(mat_key)
            prim_id += 1

    verts_all = np.concatenate(verts_all)
    norms_all = np.concatenate(norms_all)
    uvs_all = np.concatenate(uvs_all)
    part_of_vert = np.concatenate(part_of_vert)
    prim_of_vert = np.concatenate(prim_of_vert)

    hips = bone_world_pos(js, world, node_bone, "hips")
    if hips is None:
        hips = np.array([0, 1.0, 0])
    neck = bone_world_pos(js, world, node_bone, "neck")
    leg_top_r = bone_world_pos(js, world, node_bone, "rightUpperLeg")
    leg_top_l = bone_world_pos(js, world, node_bone, "leftUpperLeg")

    min_y = float(verts_all[:, 1].min())
    top_y = float(verts_all[:, 1].max())
    scale = 5.1 / max(top_y - min_y, 1e-6)

    is_vrm1 = "VRMCvrm" in js.get("extensions", {})  # VRM0 faces -Z like Roblox; VRM1 faces +Z

    def to_studs(p):
        x = (p[..., 0] - hips[0]) * scale
        y = (p[..., 1] - min_y) * scale - 3.0
        z = (p[..., 2] - hips[2]) * scale
        out = np.stack([x, y, z], axis=-1)
        if is_vrm1:
            out[..., 0] *= -1
            out[..., 2] *= -1
        return out

    studs = to_studs(verts_all)

    pivots = {}
    for pname, bone in (("Right Arm", "rightUpperArm"), ("Left Arm", "leftUpperArm")):
        w = bone_world_pos(js, world, node_bone, bone)
        pivots[pname] = to_studs(w[None, :])[0]
    arm_rot = {"Right Arm": rot_z(-ARM_ANGLE), "Left Arm": rot_z(ARM_ANGLE)}
    for pname, R in arm_rot.items():
        sel = part_of_vert == pname
        if sel.any():
            rel = studs[sel] - pivots[pname]
            studs[sel] = rel @ R.T + pivots[pname]
            norms_all[sel] = norms_all[sel] @ R.T

    centers = {
        "Torso": to_studs(hips[None, :])[0],
        "Head": to_studs((neck if neck is not None else np.array([0, 1.42, 0]))[None, :])[0],
        "Right Arm": pivots["Right Arm"],
        "Left Arm": pivots["Left Arm"],
        "Right Leg": to_studs((leg_top_r if leg_top_r is not None else hips)[None, :])[0],
        "Left Leg": to_studs((leg_top_l if leg_top_l is not None else hips)[None, :])[0],
    }

    A_all = np.concatenate([r[0] for r in tri_records])
    B_all = np.concatenate([r[1] for r in tri_records])
    C_all = np.concatenate([r[2] for r in tri_records])
    P_all = np.concatenate([np.full(len(r[0]), r[3], dtype=np.int64) for r in tri_records])
    tris_per_part = {p: [] for p in PARTS}
    for i in range(len(A_all)):
        a, b, c, prim = int(A_all[i]), int(B_all[i]), int(C_all[i]), int(P_all[i])
        votes = (part_of_vert[a], part_of_vert[b], part_of_vert[c])
        best = max(set(votes), key=lambda v: votes.count(v))
        tris_per_part[best].append((a, b, c, prim))

    atlas, placement = build_atlas(js, bin_chunk, mats_used)
    AW, AH = atlas.size
    prim_slot = {}
    for pk in range(prim_id):
        img_i, color = mats_used[prim_mat_key[pk]]
        prim_slot[pk] = (("img", img_i) if img_i is not None
                         else ("color", tuple(int(c * 255) for c in (list(color) + [1, 1, 1])[:3])))

    pad = 2
    new_uv = np.zeros_like(uvs_all)
    for pk in range(prim_id):
        sel = prim_of_vert == pk
        if not sel.any():
            continue
        x0, y0, w, h = placement[prim_slot[pk]]
        u = np.clip(uvs_all[sel, 0], 0, 1)
        v = np.clip(uvs_all[sel, 1], 0, 1)
        new_uv[sel, 0] = (u * (w - 2 * pad) + x0 + pad) / AW
        new_uv[sel, 1] = (v * (h - 2 * pad) + y0 + pad) / AH

    os.makedirs(out_dir, exist_ok=True)
    slug = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_").lower()
    atlas.save(os.path.join(out_dir, "tex.png"))

    ARM_REST = {"Right Arm": rot_z(math.radians(15)), "Left Arm": rot_z(math.radians(-15))}
    entries = []
    for pname in PARTS:
        tris = tris_per_part[pname]
        if not tris:
            continue
        center = centers[pname]
        R_rest = ARM_REST.get(pname, np.eye(3))
        dedupe = {}
        verts_out, faces_out = [], []
        for (a, b, c, prim) in tris:
            face = []
            for vi in (a, b, c):
                p = R_rest.T @ (studs[vi] - center)
                n = R_rest.T @ norms_all[vi]
                key = (round(p[0], 4), round(p[1], 4), round(p[2], 4),
                       round(new_uv[vi, 0], 4), round(new_uv[vi, 1], 4))
                i = dedupe.get(key)
                if i is None:
                    i = len(verts_out)
                    dedupe[key] = i
                    verts_out.append((p[0], p[1], p[2], n[0], n[1], n[2],
                                      new_uv[vi, 0], new_uv[vi, 1]))
                face.append(i)
            faces_out.append(tuple(face))
        write_mesh(os.path.join(out_dir, pname.replace(" ", "") + ".mesh"), verts_out, faces_out)
        arr = np.array([[v[0], v[1], v[2]] for v in verts_out])
        mn, mx = arr.min(axis=0), arr.max(axis=0)
        size = np.maximum(mx - mn, 0.2)
        origin = (mn + mx) / 2.0
        entry = {
            "part": pname,
            "mesh": f"models/{slug}/{pname.replace(' ', '')}.mesh",
            "texture": f"models/{slug}/tex.png",
            "center": [round(float(center[0]), 3), round(float(center[1]), 3), round(float(center[2]), 3)],
            "size": [round(float(size[0]), 2), round(float(size[1]), 2), round(float(size[2]), 2)],
            "origin": [round(float(o), 3) for o in origin],
        }
        if pname in ARM_REST:
            ang = math.degrees(math.atan2(ARM_REST[pname][1, 0], ARM_REST[pname][0, 0]))
            entry["rot"] = [0, 0, round(math.radians(ang), 4)]
        entries.append(entry)

    tris_render = {}
    for pname in PARTS:
        tris = tris_per_part[pname]
        if not tris:
            continue
        idxs = np.array([[t[0], t[1], t[2]] for t in tris])
        vv = np.concatenate([studs[idxs[:, k]] for k in range(3)], axis=0)
        ff = np.arange(len(idxs) * 3).reshape(-1, 3)
        uu = np.concatenate([new_uv[idxs[:, k]] for k in range(3)], axis=0)
        tris_render[pname] = (np.concatenate([vv, uu], axis=1), ff)
    render_thumb(os.path.join(out_dir, "thumb.png"), tris_render, atlas, AW, AH)

    manifest_entry = {
        "kind": "custom",
        "name": name,
        "rig": "R6",
        "thumb": f"models/{slug}/thumb.png",
        "hold": 182393478,
        "parts": entries,
    }
    with open(os.path.join(out_dir, "entry.json"), "w") as fh:
        json.dump(manifest_entry, fh, indent=2, ensure_ascii=False)
    total_tris = sum(len(v) for v in tris_per_part.values())
    print(f"{name}: {total_tris} tris, atlas {AW}x{AH}, parts written: {len(entries)}")
    return manifest_entry


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2], sys.argv[3])