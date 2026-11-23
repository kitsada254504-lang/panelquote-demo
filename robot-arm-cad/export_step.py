# -*- coding: utf-8 -*-
"""
export_step.py -- ส่งออก layout หุ่นยนต์ 4 แกนเป็นไฟล์ STEP assembly (ไม่ต้องมี SolidWorks)

ใช้พารามิเตอร์และตำแหน่งชุดเดียวกับ build_robot_arm.py (ทุกชิ้นมีชื่อ สี และตำแหน่งตามโมเดล)
เปิดใน SolidWorks / Fusion / FreeCAD ได้ทันที  หมายเหตุ: STEP เป็นของแข็งไม่ใช่พารามิเตอร์

ต้องติดตั้ง:  pip install cadquery
ตัวอย่าง:
    python export_step.py                       # ได้ output/robot_arm_layout.step
    python export_step.py --set L1=600 --out my.step
"""
import argparse
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_robot_arm as b  # noqa: E402

COLORS = {  # กลุ่ม -> (r, g, b) 0..1
    "frame": (0.80, 0.82, 0.85), "column": (0.60, 0.64, 0.70), "carriage": (0.69, 0.75, 0.84),
    "arm": (0.75, 0.84, 0.75), "purchased": (0.12, 0.15, 0.20), "bearing": (0.63, 0.66, 0.70),
    "gripper": (0.94, 0.55, 0.12),
}


def color_group(pt):
    n = pt.name
    if n.startswith(("frame", "foot", "column_base")):
        return "frame"
    if n.startswith(("column", "rail", "rack")):
        return "column"
    if n.startswith(("carriage", "platform", "blk", "pinion", "a1_shaft")):
        return "carriage"
    if n.startswith("link"):
        return "arm"
    if "bearing" in n or "hub" in n:
        return "bearing"
    if n.startswith(("gripper", "finger")):
        return "gripper"
    return "purchased"


def make_shape(cq, pt):
    """สร้างของแข็งที่ศูนย์กลางตามพิกัดจริง (mm, แกน Y ขึ้น เหมือนใน SolidWorks)"""
    ax = "XYZ".index(pt.geo["axis"])
    if pt.kind == "prism":
        dx, dy, dz = pt.geo["dims"]
        solid = cq.Workplane("XY").box(dx, dy, dz)
        w = pt.geo.get("wall")
        if w:
            dims = [dx, dy, dz]
            inner = [dims[i] + 2.0 if i == ax else max(dims[i] - 2 * w, 0.1) for i in range(3)]
            solid = solid.cut(cq.Workplane("XY").box(*inner))
    else:
        d, L = pt.geo["dia"], pt.geo["length"]
        direction = [0.0, 0.0, 0.0]
        direction[ax] = 1.0
        start = [-L / 2.0 * direction[i] for i in range(3)]
        cyl = cq.Solid.makeCylinder(d / 2.0, L, cq.Vector(*start), cq.Vector(*direction))
        solid = cq.Workplane("XY").add(cyl)
        bore = pt.geo.get("bore")
        if bore:
            hole = cq.Solid.makeCylinder(bore / 2.0, L, cq.Vector(*start), cq.Vector(*direction))
            solid = solid.cut(cq.Workplane("XY").add(hole))
    return solid.translate(pt.center)


def main(argv=None):
    ap = argparse.ArgumentParser(description="ส่งออก STEP assembly ของหุ่นยนต์ 4 แกน")
    ap.add_argument("--out", default=os.path.join("output", "robot_arm_layout.step"))
    ap.add_argument("--params", default=None, help="ไฟล์ JSON ทับพารามิเตอร์")
    ap.add_argument("--set", action="append", default=[], metavar="ชื่อ=ค่า")
    a = ap.parse_args(argv)
    try:
        import cadquery as cq
    except ImportError:
        print("ต้องติดตั้ง cadquery ก่อน:  pip install cadquery")
        return 2

    P = dict(b.PARAMS)
    if a.params:
        import json
        with open(a.params, encoding="utf-8") as f:
            P.update(json.load(f))
    for s in a.set:
        k, v = s.split("=", 1)
        if k not in P:
            ap.error("ไม่มีพารามิเตอร์ชื่อ " + k)
        P[k] = type(b.PARAMS[k])(float(v))
    parts, d, errs = b.build_design(P)
    if errs:
        print("\n".join("ผิดพลาด: " + e for e in errs))
        return 2
    ov = b.find_overlaps(parts)
    if ov:
        print("พบชิ้นส่วนซ้อนทับ %d คู่ (เช่น %s x %s) -- ยังส่งออกให้ แต่ควรแก้พารามิเตอร์" % (len(ov), ov[0][0], ov[0][1]))

    if os.path.exists(a.out):
        print("ไฟล์ %s มีอยู่แล้ว ไม่เขียนทับ ใช้ --out ชื่อใหม่" % a.out)
        return 2
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)

    asm = cq.Assembly(name="robot_arm_layout")
    for pt in parts:
        r, g, bl = COLORS[color_group(pt)]
        asm.add(make_shape(cq, pt), name=pt.name, color=cq.Color(r, g, bl))
    asm.export(a.out) if hasattr(asm, "export") else asm.save(a.out)
    print("สร้าง STEP แล้ว: %s  (%d ชิ้น, %.0f KB)" % (a.out, len(parts), os.path.getsize(a.out) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
