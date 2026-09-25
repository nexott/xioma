#!/usr/bin/env python3
"""OBJ -> Roblox .mesh converter (binary version 2.00).

Layout (matches RobloxAPI/rbxmesh reader):
  "version 2.00\\n"
  u16 headerSize=12, u8 vertexSize=36, u8 faceSize=12, u32 numVerts, u32 numFaces
  vertices: 9 x float32 (position xyz, normal xyz, uv u,v,0)
  faces:    3 x uint32 indices

Usage:
  python3 obj2mesh.py model.obj model.mesh [--scale 1.0] [--offset 0,0,0] [--no-flip-v]

Then upload the .mesh (+ texture .png) to this repo (e.g. models/mymodel/head.mesh)
and add to models/models.json:

  { "kind": "custom", "name": "My Model", "rig": "R6",
    "parts": [ { "part": "Torso", "mesh": "models/mymodel/torso.mesh",
                 "texture": "models/mymodel/torso.png" } ] }
"""
import argparse, struct, sys

def parse_obj(path):
    verts, norms, uvs, faces = [], [], [], []
    with open(path, "r", errors="ignore") as fh:
        for line in fh:
            p = line.strip().split()
            if not p:
                continue
            if p[0] == "v" and len(p) >= 4:
                verts.append(tuple(float(x) for x in p[1:4]))
            elif p[0] == "vn" and len(p) >= 4:
                norms.append(tuple(float(x) for x in p[1:4]))
            elif p[0] == "vt" and len(p) >= 3:
                uvs.append(tuple(float(x) for x in p[1:3]))
            elif p[0] == "f" and len(p) >= 4:
                idx = []
                for tok in p[1:]:
                    b = tok.split("/")
                    vi = int(b[0]) - 1 if b[0] else -1
                    ti = int(b[1]) - 1 if len(b) > 1 and b[1] else -1
                    ni = int(b[2]) - 1 if len(b) > 2 and b[2] else -1
                    idx.append((vi, ti, ni))
                for k in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[k], idx[k + 1]))
    return verts, norms, uvs, faces

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("obj")
    ap.add_argument("out")
    ap.add_argument("--scale", type=float, default=1.0, help="obj unit -> Roblox studs")
    ap.add_argument("--offset", default="0,0,0", help="extra offset x,y,z after centering")
    ap.add_argument("--flip-v", dest="flip_v", action="store_true", default=True)
    ap.add_argument("--no-flip-v", dest="flip_v", action="store_false")
    args = ap.parse_args()

    ox, oy, oz = (float(v) for v in args.offset.split(","))

    verts, norms, uvs, faces = parse_obj(args.obj)
    if not verts or not faces:
        sys.exit("obj has no vertices or faces")

    cx = sum(v[0] for v in verts) / len(verts)
    cy = sum(v[1] for v in verts) / len(verts)
    cz = sum(v[2] for v in verts) / len(verts)

    pos = [((v[0] - cx) * args.scale + ox,
            (v[1] - cy) * args.scale + oy,
            (v[2] - cz) * args.scale + oz) for v in verts]

    with open(args.out, "wb") as fh:
        fh.write(b"version 2.00\n")
        fh.write(struct.pack("<HBBII", 12, 36, 12, len(pos), len(faces)))
        for (vi, ti, ni) in faces:
            p = pos[vi] if 0 <= vi < len(pos) else (0, 0, 0)
            n = norms[ni] if 0 <= ni < len(norms) else (0.0, 0.0, 1.0)
            t = uvs[ti] if 0 <= ti < len(uvs) else (0.0, 0.0)
            tv = 1.0 - t[1] if args.flip_v else t[1]
            fh.write(struct.pack("<9f", p[0], p[1], p[2], n[0], n[1], n[2], t[0], tv, 0.0))
        for (a, b, c) in faces:
            fh.write(struct.pack("<III", a, b, c))

    print(f"wrote {args.out}: {len(pos)} verts, {len(faces)} tris")

if __name__ == "__main__":
    main()
