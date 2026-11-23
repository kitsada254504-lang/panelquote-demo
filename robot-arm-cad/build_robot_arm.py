# -*- coding: utf-8 -*-
"""
build_robot_arm.py  --  สร้างโมเดล layout หุ่นยนต์ 4 แกน (A1 Z-rack, A2, A3, A4 + Gripper)
ใน SolidWorks 2023 ผ่าน Python + pywin32

โหมดการทำงาน
  --dry-run   (ค่าเริ่มต้นถ้าไม่มี pywin32 / ไม่ใช่ Windows)
              คำนวณตำแหน่ง ตรวจการชนด้วย Python เอง ประเมินมวล ส่งออก BOM.csv ได้
              ไม่ต้องมี SolidWorks
  (ปกติ)      สร้างไฟล์ .SLDPRT ทีละชิ้น + .SLDASM แล้วตรวจก่อนเซฟ

ระบบพิกัด (mm):  X = ขวา, Y = ขึ้น, Z = ทิศที่แขนยื่นออก
  Y=0 คือพื้นโต๊ะ / ศูนย์ X อยู่กึ่งกลางเสา / ผิวหน้าเสา (ด้านรางเลื่อน) อยู่ที่ Z=0

หลักการ (ตามกฎ solidworks-com-safety-rules)
  * ไม่เขียนทับไฟล์เดิม  ทุกครั้งสร้างโฟลเดอร์ผลลัพธ์ใหม่ตามเวลา
  * ไม่เขียน Transform2  ใช้ AddComponent5 วางที่พิกัดตั้งแต่ตอนใส่ แล้ว fix
  * อ่าน Transform2 กลับมาเทียบกับค่าที่ตั้งใจก่อนเซฟ assembly
  * ตรวจการชนก่อนเซฟ  ถ้าไม่ผ่านจะไม่เซฟ assembly
  * ปิดเอกสาร part ทุกตัวก่อนจบสคริปต์

หมายเหตุ: ชิ้นส่วนที่ซื้อ (มอเตอร์ เกียร์ ลูกปืน กริปเปอร์) เป็นแค่บล็อก/ทรงกระบอก
placeholder ขนาดจริงจาก datasheet  ให้แทนด้วยไฟล์ STEP ของผู้ผลิตภายหลัง
"""
import argparse
import csv
import json
import math
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# --------------------------------------------------------------------------
# 1) พารามิเตอร์ (mm, kg)  --  แก้ที่นี่ หรือใช้ --set ชื่อ=ค่า / --params ไฟล์.json
# --------------------------------------------------------------------------
PARAMS = dict(
    # โครงฐาน
    base_w=450.0, base_d=450.0, prof=40.0, prof_wall=4.0, foot_h=30.0, foot_d=40.0, inner_x=100.0,
    bp_w=220.0, bp_d=220.0, bp_t=10.0,          # แผ่นฐาน 220x220 ใต้เสา (ตามรูป)
    # เสา 4080
    col_w=80.0, col_d=40.0, col_len=1500.0, col_wall=4.0,
    # รางเลื่อน HGR15 + บล็อก (บล็อกโมเดลเฉพาะส่วนเหนือหัวราง)
    rail_len=1300.0, rail_w=15.0, rail_h=15.0, rail_x=25.0,
    blk_len=62.4, blk_w=34.0, blk_top=28.0, blk_dv=130.0, rail_margin=10.0,
    # ช่วงชัก Z และตำแหน่งตอนสร้าง (0 = ล่างสุด, 1 = บนสุด)
    stroke=900.0, home_frac=0.5, clear_table=20.0,
    # แผ่นแคร่และแท่นรับแขน
    plate_w=160.0, plate_h=200.0, plate_t=10.0, plat_w=200.0, plat_d=200.0, plat_t=10.0,
    # เฟืองสะพาน M1.5 15x15 และพิเนียน (โมเดลที่ขนาดรากฟัน ไม่มีฟัน กันชนเทียม)
    rack_h=15.0, rack_w=15.0, rack_len=1000.0, mod=1.5, pin_z=20, pin_face=20.0, shaft_d=14.0,
    # มอเตอร์/เกียร์ NEMA23 (A1-A3)
    gb_sq=60.0, gb_len=62.0, m23_sq=56.4, m23_len=82.0, brake_d=70.0, brake_len=30.0, gb_dy=60.0,
    # ข้อหมุน A2, A3
    brg_d=150.0, brg_h=20.0, hub_d=110.0, hub_h=30.0, L1=550.0, L2=450.0, link_ext=20.0,
    # ลิงก์ 1 = 8020 (ตามรูป: วาง 80 ตั้ง 20 กว้าง ต้านการแอ่งจากน้ำหนัก) / ลิงก์ 2 ใช้ 4040 (ผู้ใช้ยืนยันแล้ว)
    link1_x=20.0, link1_y=80.0, link1_wall=3.0,
    # A4 (NEMA17) และกริปเปอร์
    gb17_sq=42.0, gb17_len=45.0, m17_len=48.0,
    grip_w=60.0, grip_h=130.0, grip_d=60.0, finger_t=12.0, finger_h=50.0, finger_d=16.0, grip_open=60.0,
    # ค่าใช้ในการวิเคราะห์โหลด (ไม่มีผลต่อรูปทรง)
    payload=1.0, E_gpa=70.0, motor_T=3.0, motor_derate=0.5,
    a2_ratio=10.0, a3_ratio=10.0, gear_eff=0.8, alpha=5.0,
)

DENSITY = {"AL6061": 2.70, "STEEL": 7.85, "PLACEHOLDER": 7.85}   # g/cm3
SW_MATERIAL = {"AL6061": "6061 Alloy", "STEEL": "Plain Carbon Steel", "PLACEHOLDER": "Plain Carbon Steel"}
AXIS_SKETCH = {"Z": ("Front Plane", 0, 1), "Y": ("Top Plane", 0, 2), "X": ("Right Plane", 2, 1)}
# ^ แกนที่ extrude -> (ชื่อ plane, index ของมิติบน sketch x, index ของมิติบน sketch y) ; index 0=X 1=Y 2=Z


class Part(object):
    def __init__(self, name, file, kind, center, material, group, note, mass, geo):
        self.name, self.file, self.kind = name, file, kind
        self.center, self.material, self.group = tuple(center), material, group
        self.note, self.mass_target, self.geo = note, mass, geo

    # ----- เรขาคณิต -----
    def size(self):
        if self.kind == "prism":
            return tuple(self.geo["dims"])
        d, L, ax = self.geo["dia"], self.geo["length"], self.geo["axis"]
        s = [d, d, d]
        s["XYZ".index(ax)] = L
        return tuple(s)

    def aabb(self):
        s = self.size()
        return (tuple(self.center[i] - s[i] / 2.0 for i in range(3)),
                tuple(self.center[i] + s[i] / 2.0 for i in range(3)))

    def volume_mm3(self):
        if self.kind == "prism":
            dx, dy, dz = self.geo["dims"]
            ax = "XYZ".index(self.geo["axis"])
            v = dx * dy * dz
            w = self.geo.get("wall")
            if w:
                dims = [dx, dy, dz]
                inner = 1.0
                for i in range(3):
                    inner *= dims[i] if i == ax else max(dims[i] - 2 * w, 0.0)
                v -= inner
            return v
        d, L = self.geo["dia"], self.geo["length"]
        v = math.pi / 4.0 * d * d * L
        b = self.geo.get("bore")
        if b:
            v -= math.pi / 4.0 * b * b * L
        return v

    def mass_kg(self):
        if self.mass_target is not None:
            return self.mass_target
        return self.volume_mm3() / 1000.0 * DENSITY[self.material] / 1000.0

    def geo_signature(self):
        return (self.kind, tuple(sorted((k, tuple(v) if isinstance(v, (list, tuple)) else v)
                                        for k, v in self.geo.items())), self.material)


# --------------------------------------------------------------------------
# 2) ออกแบบ layout (ล้วน Python  ทดสอบได้โดยไม่ต้องมี SolidWorks)
# --------------------------------------------------------------------------
def derive(p):
    d = {}
    d["frame_top"] = p["foot_h"] + p["prof"]
    d["rail_bot"] = d["frame_top"] + p["bp_t"]        # เสาตั้งบนแผ่นฐาน
    half = p["rail_margin"] + p["blk_len"] / 2.0 + p["blk_dv"] / 2.0
    d["yc_rail_min"] = d["rail_bot"] + half
    d["yc_rail_max"] = d["rail_bot"] + p["rail_len"] - half
    # ลึกจาก y_c ถึงปลายนิ้วกริปเปอร์
    y_p_rel = -p["plate_h"] / 2.0 + p["plat_t"]
    link1_top_rel = y_p_rel + p["brg_h"] + p["hub_h"] + p["link1_y"]
    link2_bot_rel = link1_top_rel + p["brg_h"] + p["hub_h"]
    d["tip_rel"] = link2_bot_rel - p["grip_h"] - p["finger_h"]
    d["yc_low"] = max(d["yc_rail_min"],
                      d["rail_bot"] + p["plate_h"] / 2.0 + 10.0,
                      -d["tip_rel"] + p["clear_table"])
    d["stroke_max"] = d["yc_rail_max"] - d["yc_low"]
    d["yc"] = d["yc_low"] + p["home_frac"] * p["stroke"]
    d["pin_x"] = p["col_w"] / 2.0 + p["rack_h"] - p["mod"] + p["mod"] * p["pin_z"] / 2.0
    d["pin_dia"] = p["mod"] * (p["pin_z"] - 2.5)
    return d


def build_design(P):
    p = dict(P)
    d = derive(p)
    errs = []
    if p["stroke"] > d["stroke_max"] + 1e-6:
        errs.append("ช่วงชัก %.0f mm เกินค่าที่รางรองรับได้ %.0f mm" % (p["stroke"], d["stroke_max"]))
    if p["rack_len"] < p["stroke"] + p["pin_face"] + 10:
        errs.append("เฟืองสะพาน %.0f mm สั้นกว่าช่วงชัก + หน้ากว้างพิเนียน" % p["rack_len"])
    if p["col_len"] < p["rail_len"]:
        errs.append("เสาสั้นกว่ารางเลื่อน")

    yc = d["yc"]
    parts = []

    def add(name, file, kind, c, mat, group, note="", mass=None, **geo):
        parts.append(Part(name, file, kind, c, mat, group, note, mass, geo))

    pw, w = p["prof"], p["prof_wall"]
    yf = p["foot_h"] + pw / 2.0
    zr = -pw / 2.0
    zf = p["base_d"] - 1.5 * pw
    sx = p["base_w"] / 2.0 - pw / 2.0
    side_len = p["base_d"] - 2 * pw
    zs = side_len / 2.0

    # ---- โครงฐาน (4040 กลวง ผนัง 4 mm ประมาณมวล ~1.5 kg/m) ----
    add("frame_rear", "frame_x", "prism", (0, yf, zr), "AL6061", "frame",
        dims=(p["base_w"], pw, pw), axis="X", wall=w)
    add("frame_front", "frame_x", "prism", (0, yf, zf), "AL6061", "frame",
        dims=(p["base_w"], pw, pw), axis="X", wall=w)
    for nm, x in (("frame_side_L", -sx), ("frame_side_R", sx), ("frame_inner_L", -p["inner_x"]),
                  ("frame_inner_R", p["inner_x"])):
        add(nm, "frame_z", "prism", (x, yf, zs), "AL6061", "frame",
            dims=(pw, pw, side_len), axis="Z", wall=w)
    for i, (x, z) in enumerate(((-sx, zr), (sx, zr), (-sx, zf), (sx, zf)), 1):
        add("foot_%d" % i, "foot", "cyl", (x, p["foot_h"] / 2.0, z), "STEEL", "frame", "ขาปรับระดับ M10",
            0.08, dia=p["foot_d"], length=p["foot_h"], axis="Y")

    # ---- แผ่นฐาน 220x220 ใต้เสา (วางบนโปรไฟล์ฐาน: ท้ายแผ่นชนขอบหลังของโครง) ----
    add("column_base_plate", "base_plate", "prism",
        (0, d["frame_top"] + p["bp_t"] / 2.0, -pw + p["bp_d"] / 2.0), "AL6061", "static",
        "แผ่นฐานใต้เสา 220x220 (ยังไม่เจาะรู)", dims=(p["bp_w"], p["bp_t"], p["bp_d"]), axis="Y", wall=None)

    # ---- เสา 4080 + ราง + เฟืองสะพาน ----
    add("column", "column", "prism", (0, d["rail_bot"] + p["col_len"] / 2.0, -p["col_d"] / 2.0), "AL6061", "static",
        "เสา 4080", dims=(p["col_w"], p["col_len"], p["col_d"]), axis="Y", wall=p["col_wall"])
    for nm, x in (("rail_L", -p["rail_x"]), ("rail_R", p["rail_x"])):
        add(nm, "rail", "prism", (x, d["rail_bot"] + p["rail_len"] / 2.0, p["rail_h"] / 2.0), "STEEL", "static",
            "ราง HGR15", dims=(p["rail_w"], p["rail_len"], p["rail_h"]), axis="Y", wall=None)
    add("rack", "rack", "prism",
        (p["col_w"] / 2.0 + p["rack_h"] / 2.0, yc + p["gb_dy"], -p["col_d"] / 2.0), "STEEL", "static",
        "เฟืองสะพาน M1.5 (โมเดลทึบ ไม่มีฟัน)", dims=(p["rack_h"], p["rack_len"], p["rack_w"]), axis="Y", wall=None)

    # ---- แคร่ Z (เคลื่อนที่ไปกับแกน Z ทั้งหมดต่อจากนี้) ----
    bt = p["blk_top"] - p["rail_h"]
    for sgn, tag in ((-1, "L"), (1, "R")):
        for pos, tag2 in ((-1, "lo"), (1, "hi")):
            add("blk_%s_%s" % (tag, tag2), "blk", "prism",
                (sgn * p["rail_x"], yc + pos * p["blk_dv"] / 2.0, p["rail_h"] + bt / 2.0), "STEEL", "Z",
                "บล็อก HGH15CA (เฉพาะส่วนเหนือหัวราง)", 0.18,
                dims=(p["blk_w"], p["blk_len"], bt), axis="Y", wall=None)
    plate_front = p["blk_top"] + p["plate_t"]
    add("carriage_plate", "carriage_plate", "prism", (0, yc, p["blk_top"] + p["plate_t"] / 2.0), "AL6061", "Z",
        "แผ่นแคร่ (ยังไม่เจาะรู)", dims=(p["plate_w"], p["plate_h"], p["plate_t"]), axis="Z", wall=None)
    py = yc + p["gb_dy"]
    add("pinion", "pinion", "cyl", (d["pin_x"], py, -p["col_d"] / 2.0), "STEEL", "Z",
        "พิเนียน %d ฟัน M%.1f (โมเดลที่ขนาดรากฟัน)" % (p["pin_z"], p["mod"]),
        dia=d["pin_dia"], length=p["pin_face"], axis="Z")
    z0, z1 = -p["col_d"] / 2.0 + p["pin_face"] / 2.0, p["blk_top"]
    add("a1_shaft", "a1_shaft", "cyl", (d["pin_x"], py, (z0 + z1) / 2.0), "STEEL", "Z",
        "เพลาเอาต์พุตเกียร์ A1 ทะลุแผ่นแคร่ (ยังไม่เจาะรูในแผ่น)", dia=p["shaft_d"], length=z1 - z0, axis="Z")
    add("a1_gearbox", "gb_z", "prism", (d["pin_x"], py, plate_front + p["gb_len"] / 2.0), "PLACEHOLDER", "Z",
        "เกียร์ดาวเคราะห์ NEMA23 5:1", 1.1, dims=(p["gb_sq"], p["gb_sq"], p["gb_len"]), axis="Z", wall=None)
    add("a1_motor", "m23_z", "prism", (d["pin_x"], py, plate_front + p["gb_len"] + p["m23_len"] / 2.0),
        "PLACEHOLDER", "Z", "มอเตอร์ NEMA23 23HS45-4204D-E1000", 1.2,
        dims=(p["m23_sq"], p["m23_sq"], p["m23_len"]), axis="Z", wall=None)
    add("a1_brake", "brake", "cyl",
        (d["pin_x"], py, plate_front + p["gb_len"] + p["m23_len"] + p["brake_len"] / 2.0), "PLACEHOLDER", "Z",
        "เบรก 24V ท้ายมอเตอร์ (ตรวจว่าท้ายมอเตอร์ว่างหรือไม่ ชน encoder หรือเปล่า)", 0.35,
        dia=p["brake_d"], length=p["brake_len"], axis="Z")

    # ---- แท่นรับแขน + A2 ----
    y_p = yc - p["plate_h"] / 2.0 + p["plat_t"]
    zA2 = plate_front + p["plat_d"] / 2.0
    add("platform", "platform", "prism", (0, y_p - p["plat_t"] / 2.0, zA2), "AL6061", "Z", "แท่นรับแขน",
        dims=(p["plat_w"], p["plat_t"], p["plat_d"]), axis="Y", wall=None)

    def joint(tag, zc, y0):
        add("%s_bearing" % tag, "bearing", "cyl", (0, y0 + p["brg_h"] / 2.0, zc), "PLACEHOLDER", "Z",
            "ลูกปืนแท่นหมุน Ø150", 0.8, dia=p["brg_d"], length=p["brg_h"], axis="Y")
        add("%s_hub" % tag, "hub", "cyl", (0, y0 + p["brg_h"] + p["hub_h"] / 2.0, zc), "AL6061", "Z",
            "ฮับข้อหมุน (กลึงเอง)", dia=p["hub_d"], length=p["hub_h"], axis="Y")
        return y0 + p["brg_h"] + p["hub_h"]

    def drive_y(tag, zc, ytop, gb_mass):
        add("%s_gearbox" % tag, "gb_y", "prism", (0, ytop + p["gb_len"] / 2.0, zc), "PLACEHOLDER", "Z",
            "เกียร์ดาวเคราะห์ NEMA23 10:1", gb_mass, dims=(p["gb_sq"], p["gb_len"], p["gb_sq"]), axis="Y", wall=None)
        add("%s_motor" % tag, "m23_y", "prism", (0, ytop + p["gb_len"] + p["m23_len"] / 2.0, zc), "PLACEHOLDER", "Z",
            "มอเตอร์ NEMA23", 1.2, dims=(p["m23_sq"], p["m23_len"], p["m23_sq"]), axis="Y", wall=None)

    l1_bot = joint("a2", zA2, y_p)
    add("link1", "link1", "prism", (0, l1_bot + p["link1_y"] / 2.0, zA2 + p["L1"] / 2.0), "AL6061", "Z",
        "ลิงก์ 1 โปรไฟล์ 8020 (วาง 80 ตั้ง)",
        dims=(p["link1_x"], p["link1_y"], p["L1"] + 2 * p["link_ext"]), axis="Z", wall=p["link1_wall"])
    l1_top = l1_bot + p["link1_y"]
    drive_y("a2", zA2, l1_top, 1.2)

    zA3 = zA2 + p["L1"]
    l2_bot = joint("a3", zA3, l1_top)
    add("link2", "link2", "prism", (0, l2_bot + pw / 2.0, zA3 + p["L2"] / 2.0), "AL6061", "Z",
        "ลิงก์ 2 โปรไฟล์ 4040", dims=(pw, pw, p["L2"] + 2 * p["link_ext"]), axis="Z", wall=w)
    l2_top = l2_bot + pw
    drive_y("a3", zA3, l2_top, 1.2)

    # ---- A4 + กริปเปอร์ ----
    zA4 = zA3 + p["L2"]
    add("a4_gearbox", "gb17", "prism", (0, l2_top + p["gb17_len"] / 2.0, zA4), "PLACEHOLDER", "Z",
        "เกียร์ NEMA17 5:1", 0.4, dims=(p["gb17_sq"], p["gb17_len"], p["gb17_sq"]), axis="Y", wall=None)
    add("a4_motor", "m17", "prism", (0, l2_top + p["gb17_len"] + p["m17_len"] / 2.0, zA4), "PLACEHOLDER", "Z",
        "มอเตอร์ NEMA17", 0.35, dims=(p["gb17_sq"], p["m17_len"], p["gb17_sq"]), axis="Y", wall=None)
    add("gripper_body", "grip_body", "prism", (0, l2_bot - p["grip_h"] / 2.0, zA4), "PLACEHOLDER", "Z",
        "กริปเปอร์ 2 นิ้ว (บล็อกตัวแทน)", 0.8,
        dims=(p["grip_w"], p["grip_h"], p["grip_d"]), axis="Y", wall=None)
    for sgn, tag in ((-1, "L"), (1, "R")):
        add("finger_%s" % tag, "finger", "prism",
            (sgn * (p["grip_open"] / 2.0 + p["finger_t"] / 2.0), l2_bot - p["grip_h"] - p["finger_h"] / 2.0, zA4),
            "PLACEHOLDER", "Z", "นิ้วกริปเปอร์", 0.03,
            dims=(p["finger_t"], p["finger_h"], p["finger_d"]), axis="Y", wall=None)

    # ไฟล์เดียวกันต้องเรขาคณิตเหมือนกัน
    sig = {}
    for pt in parts:
        s = pt.geo_signature()
        if sig.setdefault(pt.file, s) != s:
            errs.append("ไฟล์ %s ถูกใช้กับเรขาคณิตต่างกัน (%s)" % (pt.file, pt.name))
    return parts, d, errs


# --------------------------------------------------------------------------
# 3) ตรวจ layout ด้วย Python (AABB)  ชนกันจริง = ซ้อนทับปริมาตรมากกว่า tol
# --------------------------------------------------------------------------
def find_overlaps(parts, tol=0.01):
    out = []
    boxes = [(pt, pt.aabb()) for pt in parts]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, (amin, amax) = boxes[i]
            b, (bmin, bmax) = boxes[j]
            ov = [min(amax[k], bmax[k]) - max(amin[k], bmin[k]) for k in range(3)]
            if all(o > tol for o in ov):
                out.append((a.name, b.name, ov[0] * ov[1] * ov[2]))
    return out


def analyze(parts, d, p, log):
    """วิเคราะห์โหลดคร่าว ๆ จากมวลและตำแหน่งใน layout (ท่า home แขนเหยียดตรง) คืนค่าเป็น dict"""
    g = 9.81
    by = dict((pt.name, pt) for pt in parts)
    tip = by["gripper_body"]
    pay = p["payload"]
    pts = [(pt.mass_kg(), pt.center) for pt in parts] + [(pay, (0.0, tip.center[1], tip.center[2]))]
    r = {}
    r["mass_total"] = sum(m for m, _ in pts)
    # พลิกคว่ำรอบขอบหน้าของขาตั้ง
    edge = p["base_d"] - 1.5 * p["prof"] + p["foot_d"] / 2.0
    r["M_over"] = sum(m * g * (c[2] - edge) / 1000.0 for m, c in pts if c[2] > edge)
    r["M_stab"] = sum(m * g * (edge - c[2]) / 1000.0 for m, c in pts if c[2] <= edge)
    r["SF_tip"] = r["M_stab"] / r["M_over"] if r["M_over"] > 0 else float("inf")
    # โมเมนต์ที่คาร์เรจ (รอบแกนกลางเสา) และการแอ่งของเสา (ดัดรอบแกนอ่อน = ความลึก col_d)
    zg = [(pt.mass_kg(), pt.center) for pt in parts if pt.group == "Z"] + [(pay, (0.0, tip.center[1], tip.center[2]))]
    r["m_Z"] = sum(m for m, _ in zg)
    r["M_car"] = sum(m * g * (c[2] + p["col_d"] / 2.0) / 1000.0 for m, c in zg)
    w_, dd, t = p["col_w"], p["col_d"], p["col_wall"]
    I_mm4 = (w_ * dd ** 3 - (w_ - 2 * t) * (dd - 2 * t) ** 3) / 12.0
    r["I_col_cm4"] = I_mm4 / 1e4
    EI = p["E_gpa"] * 1e9 * I_mm4 * 1e-12
    reach = (p["L1"] + p["L2"]) / 1000.0
    a_mid = (d["yc"] - d["rail_bot"]) / 1000.0
    a_top = a_mid + p["stroke"] / 2000.0
    r["droop_mid_mm"] = r["M_car"] * a_mid / EI * reach * 1000.0
    r["droop_top_mm"] = r["M_car"] * a_top / EI * reach * 1000.0
    # ข้อหมุน A2, A3  (มวลลิงก์จากโมเดล)
    L1, L2 = p["L1"] / 1000.0, p["L2"] / 1000.0
    ml1, ml2 = by["link1"].mass_kg(), by["link2"].mass_kg()
    mA3 = sum(by["a3_" + k].mass_kg() for k in ("motor", "gearbox", "bearing"))
    mend = (by["a4_motor"].mass_kg() + by["a4_gearbox"].mass_kg() + by["gripper_body"].mass_kg()
            + by["finger_L"].mass_kg() + by["finger_R"].mass_kg() + pay)
    I2 = ml1 * L1 ** 2 / 3 + mA3 * L1 ** 2 + ml2 * (L1 ** 2 + L1 * L2 + L2 ** 2 / 3) + mend * (L1 + L2) ** 2
    I3 = ml2 * L2 ** 2 / 3 + mend * L2 ** 2
    avail = p["motor_T"] * p["motor_derate"]
    r["I_A2"], r["I_A3"] = I2, I3
    for tag, I_, ratio in (("A2", I2, p["a2_ratio"]), ("A3", I3, p["a3_ratio"])):
        T = I_ * p["alpha"] / ratio / p["gear_eff"]
        r["T_" + tag] = T
        r["SF_" + tag] = avail / T
        amax = avail / 2.0 * ratio * p["gear_eff"] / I_
        r["alpha_max_" + tag] = amax
        r["t90_" + tag] = 2.0 * math.sqrt((math.pi / 2.0) / amax)
    r["alpha_max_A2_x2"] = r["alpha_max_A2"] * 2.0          # ถ้าเกียร์ A2 ทดเพิ่มเป็น 2 เท่า
    r["Mb_A2"] = (ml1 * L1 / 2 + mA3 * L1 + ml2 * (L1 + L2 / 2) + mend * (L1 + L2)) * g
    r["Mb_A3"] = (ml2 * L2 / 2 + mend * L2) * g
    log("-" * 78)
    log("วิเคราะห์โหลดคร่าว ๆ (ท่า home แขนเหยียดตรง / มวลเป็นค่าประเมิน)")
    log("  มวลเครื่องรวม (รวม payload %.1f kg) = %.1f kg" % (pay, r["mass_total"]))
    log("  พลิกคว่ำรอบขอบหน้า z=%.0f: โมเมนต์พลิก %.1f N·m / ต้าน %.1f N·m = %.2f เท่า (ต้องการ >= 2)"
        % (edge, r["M_over"], r["M_stab"], r["SF_tip"]))
    log("  แคร่ Z: มวลที่ยก %.1f kg โมเมนต์รอบแกนเสา %.1f N·m" % (r["m_Z"], r["M_car"]))
    log("  เสา I(แกนอ่อน)=%.1f cm4: ปลายแขนตกจากการแอ่งของเสา ≈ %.1f mm (กลางช่วงชัก) / %.1f mm (บนสุด)"
        % (r["I_col_cm4"], r["droop_mid_mm"], r["droop_top_mm"]))
    for tag, ratio in (("A2", p["a2_ratio"]), ("A3", p["a3_ratio"])):
        log("  %s เกียร์ %.0f:1  I=%.2f kg·m²  ที่ α=%.1f rad/s² ต้องการ %.2f N·m (ใช้ได้ %.2f) ปลอดภัย %.2f เท่า"
            % (tag, ratio, r["I_" + tag], p["alpha"], r["T_" + tag], avail, r["SF_" + tag]))
        log("      α สูงสุดที่ยังปลอดภัย 2 เท่า = %.2f rad/s²  (หมุน 90° ≈ %.1f วินาที)"
            % (r["alpha_max_" + tag], r["t90_" + tag]))
    log("  โมเมนต์สถิตที่ลูกปืน A2 = %.1f N·m, A3 = %.1f N·m (เทียบพิกัดใน datasheet)" % (r["Mb_A2"], r["Mb_A3"]))
    return r


def report(parts, d, p, log):
    log("=" * 78)
    log("สรุป layout (หน่วย mm / kg)")
    log("  ตำแหน่งแคร่ Z ตอนสร้าง y_c = %.1f  (ต่ำสุด %.1f, ช่วงชักที่รางให้ได้ %.0f, ตั้งไว้ %.0f)"
        % (d["yc"], d["yc_low"], d["stroke_max"], p["stroke"]))
    log("  พิเนียน %d ฟัน M%.1f: x=%.1f  dia รากฟัน=%.2f" % (p["pin_z"], p["mod"], d["pin_x"], d["pin_dia"]))
    lo = [min(pt.aabb()[0][i] for pt in parts) for i in range(3)]
    hi = [max(pt.aabb()[1][i] for pt in parts) for i in range(3)]
    log("  ขอบเขตรวม  X %.0f..%.0f  Y %.0f..%.0f  Z %.0f..%.0f   (กว้าง %.0f × สูง %.0f × ลึก %.0f)"
        % (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2], hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]))
    total = sum(pt.mass_kg() for pt in parts)
    zmass = sum(pt.mass_kg() for pt in parts if pt.group == "Z")
    log("  มวลรวมโดยประมาณ %.1f kg   มวลที่แกน Z ยก (ยังไม่รวม payload) %.1f kg" % (total, zmass))
    log("  (มวล placeholder ใช้ค่าตั้งเอง  มวลที่ SolidWorks คำนวณจากปริมาตรจะต่างออกไป)")
    log("-" * 78)
    log("%-16s %-10s %-9s %-26s %-28s %7s" % ("ชื่อ", "ไฟล์", "วัสดุ", "ขนาด (x,y,z)", "ศูนย์กลาง (x,y,z)", "kg"))
    for pt in parts:
        s = pt.size()
        log("%-16s %-10s %-9s %-26s %-28s %7.2f" % (
            pt.name, pt.file, pt.material,
            "%.1f×%.1f×%.1f" % s, "%.1f,%.1f,%.1f" % pt.center, pt.mass_kg()))


def export_files(parts, d, p, outdir, analysis=None):
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "BOM_layout.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ชื่อ", "ไฟล์", "ชนิด", "x_mm", "y_mm", "z_mm", "ขนาด/dia_mm", "วัสดุ", "มวล_kg", "กลุ่ม", "หมายเหตุ"])
        for pt in parts:
            w.writerow([pt.name, pt.file + ".SLDPRT", pt.kind] + ["%.2f" % v for v in pt.center]
                       + ["%.1f×%.1f×%.1f" % pt.size(), pt.material, "%.3f" % pt.mass_kg(), pt.group, pt.note])
    with open(os.path.join(outdir, "params_used.json"), "w", encoding="utf-8") as f:
        json.dump({"params": p, "derived": d, "analysis": analysis}, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# 4) ส่วน SolidWorks (ต้องรันบน Windows ที่ติดตั้ง SolidWorks 2023 + pywin32)
# --------------------------------------------------------------------------
def prop(obj, name):
    """อ่าน property/method ไม่มีอาร์กิวเมนต์ ได้ทั้งสองแบบ (late binding)"""
    v = getattr(obj, name)
    return v() if callable(v) else v


def connect_sw():
    import win32com.client as win32
    try:
        sw = win32.GetActiveObject("SldWorks.Application")
    except Exception:
        sw = win32.Dispatch("SldWorks.Application")
    sw.Visible = True
    return sw


def get_template(sw, kind):
    idx = 8 if kind == "part" else 9       # swDefaultTemplatePart / swDefaultTemplateAssembly
    try:
        t = sw.GetUserPreferenceStringValue(idx)
    except Exception:
        t = ""
    if t and os.path.exists(t):
        return t
    base = r"C:\ProgramData\SolidWorks\SOLIDWORKS 2023\templates"
    t = os.path.join(base, "Part.prtdot" if kind == "part" else "Assembly.asmdot")
    if os.path.exists(t):
        return t
    raise RuntimeError("ไม่พบ template %s  ตั้งที่ Tools > Options > Default Templates" % kind)


def select_plane(model, axis):
    name = AXIS_SKETCH[axis][0]
    if model.Extension.SelectByID2(name, "PLANE", 0, 0, 0, False, 0, None, 0):
        return
    planes, f = [], model.FirstFeature()          # SolidWorks ภาษาอื่น: ใช้ลำดับ 3 ระนาบแรก (Front, Top, Right)
    while f is not None:
        if f.GetTypeName2() == "RefPlane":
            planes.append(f)
        f = f.GetNextFeature()
    idx = {"Z": 0, "Y": 1, "X": 2}[axis]
    if len(planes) <= idx or not model.Extension.SelectByID2(planes[idx].Name, "PLANE", 0, 0, 0, False, 0, None, 0):
        raise RuntimeError("เลือกระนาบ %s ไม่สำเร็จ" % name)


def build_part_sw(sw, pt, outdir, log):
    """สร้าง part หนึ่งชิ้น (sketch กึ่งกลางที่ origin แล้ว extrude แบบ Mid Plane) -> คืน path ที่เซฟ"""
    model = sw.NewDocument(get_template(sw, "part"), 0, 0, 0)
    if model is None:
        raise RuntimeError("สร้างเอกสาร part ไม่สำเร็จ")
    path = os.path.join(outdir, pt.file + ".SLDPRT")
    try:
        ax = pt.geo["axis"]
        select_plane(model, ax)
        sk = model.SketchManager
        sk.InsertSketch(True)
        if pt.kind == "prism":
            dims = pt.geo["dims"]
            ia, ib = AXIS_SKETCH[ax][1], AXIS_SKETCH[ax][2]
            a, b = dims[ia] / 2000.0, dims[ib] / 2000.0
            sk.CreateCenterRectangle(0, 0, 0, a, b, 0)
            w = pt.geo.get("wall")
            if w:
                sk.CreateCenterRectangle(0, 0, 0, a - w / 1000.0, b - w / 1000.0, 0)
            length = dims["XYZ".index(ax)]
        else:
            sk.CreateCircleByRadius(0, 0, 0, pt.geo["dia"] / 2000.0)
            if pt.geo.get("bore"):
                sk.CreateCircleByRadius(0, 0, 0, pt.geo["bore"] / 2000.0)
            length = pt.geo["length"]
        sk.InsertSketch(True)
        if not model.Extension.SelectByID2("Sketch1", "SKETCH", 0, 0, 0, False, 0, None, 0):
            log("   เตือน: เลือก Sketch1 ไม่สำเร็จ (ใช้ selection เดิมต่อ)")
        feat = model.FeatureManager.FeatureExtrusion3(
            True, False, False, 7, 0, length / 1000.0, 0.0,      # 7 = Mid Plane
            False, False, False, False, 0, 0, False, False, False, False,
            True, True, True, 0, 0, False)
        if feat is None:
            raise RuntimeError("Extrude ล้มเหลว (%s)" % pt.file)
        try:
            model.SetMaterialPropertyName2("", r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\english\sldmaterials.sldmat",
                                           SW_MATERIAL[pt.material])
        except Exception:
            log("   เตือน: ตั้งวัสดุ %s ไม่สำเร็จ (ตั้งเองภายหลังได้)" % pt.material)
        model.EditRebuild3()
        res = model.SaveAs3(path, 0, 1)
        log("   เซฟ %s -> %r" % (os.path.basename(path), (res,)))
    finally:
        try:
            sw.CloseDoc(prop(model, "GetTitle"))
        except Exception:
            pass
    if not os.path.exists(path):
        raise RuntimeError("ไม่พบไฟล์ที่เซฟ: " + path)
    return path


def sw_interference_volume(asm, log):
    """ปริมาตรชนรวม (mm3) หรือ None ถ้าตรวจไม่ได้  (ใช้เป็นรายงาน ไม่ใช่ตัวตัดสินเดียว)"""
    try:
        mgr = asm.InterferenceDetectionManager
        mgr.TreatCoincidenceAsInterference = False
        mgr.TreatSubAssembliesAsComponents = True
        mgr.IncludeMultibodyPartInterferences = False
        mgr.MakeInterferingPartsTransparent = False
        mgr.CreateFastenersFolder = False
        items = mgr.GetInterferences() or []
        vol = sum(i.Volume for i in items) * 1e9      # m3 -> mm3
        mgr.Done()
        return vol
    except Exception as e:
        log("   (ตรวจ interference ใน SolidWorks ไม่ได้: %s)" % e)
        return None


def build_assembly_sw(sw, parts, paths, outdir, log, tol_mm=0.05):
    asm = sw.NewDocument(get_template(sw, "asm"), 0, 0, 0)
    if asm is None:
        raise RuntimeError("สร้าง assembly ไม่สำเร็จ")
    try:
        bad = []
        for pt in parts:
            x, y, z = [v / 1000.0 for v in pt.center]
            comp = asm.AddComponent5(paths[pt.file], 0, "", False, "", x, y, z)
            if comp is None:
                raise RuntimeError("ใส่ component %s ไม่สำเร็จ" % pt.name)
            comp.Select4(False, None, False)
            asm.FixComponent()
            asm.ClearSelection2(True)
            got = comp.Transform2.ArrayData            # อ่านเท่านั้น ห้ามเขียน
            gx, gy, gz = got[9] * 1000.0, got[10] * 1000.0, got[11] * 1000.0
            err = max(abs(gx - pt.center[0]), abs(gy - pt.center[1]), abs(gz - pt.center[2]))
            log("   %-16s ตั้งใจ (%.1f, %.1f, %.1f)  ได้ (%.1f, %.1f, %.1f)  %s" % (
                pt.name, pt.center[0], pt.center[1], pt.center[2], gx, gy, gz, "OK" if err <= tol_mm else "ผิด!"))
            if err > tol_mm:
                bad.append(pt.name)
        asm.EditRebuild3()
        vol = sw_interference_volume(asm, log)
        if vol is not None:
            log("   interference รวมใน SolidWorks = %.2f mm3" % vol)
        ok = (not bad) and (vol is None or vol <= 0.01)
        asm_path = os.path.join(outdir, "robot_arm_layout.SLDASM")
        if not ok:
            log("ไม่ผ่าน (%s) -- ไม่เซฟ assembly" % (("ตำแหน่งผิด: " + ", ".join(bad)) if bad else "มี interference"))
            return None
        res = asm.SaveAs3(asm_path, 0, 1)
        log("เซฟ assembly -> %r  %s" % ((res,), asm_path))
        return asm_path
    finally:
        try:
            sw.CloseDoc(prop(asm, "GetTitle"))
        except Exception:
            pass


# --------------------------------------------------------------------------
# 5) main
# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="สร้าง layout หุ่นยนต์ 4 แกนใน SolidWorks 2023")
    ap.add_argument("--dry-run", action="store_true", help="ไม่แตะ SolidWorks  คำนวณ/ตรวจ/ส่งออก CSV เท่านั้น")
    ap.add_argument("--outdir", default=None, help="โฟลเดอร์ผลลัพธ์ (ค่าเริ่มต้น: ./output/robot_arm_<เวลา>)")
    ap.add_argument("--params", default=None, help="ไฟล์ JSON ทับค่าพารามิเตอร์")
    ap.add_argument("--set", action="append", default=[], metavar="ชื่อ=ค่า", help="ทับพารามิเตอร์ เช่น --set L1=320")
    ap.add_argument("--force", action="store_true", help="ทำต่อแม้ตรวจเจอชนใน Python (ไม่แนะนำ)")
    ap.add_argument("--dump-params", action="store_true", help="พิมพ์พารามิเตอร์ทั้งหมดเป็น JSON แล้วออก")
    a = ap.parse_args(argv)

    P = dict(PARAMS)
    if a.params:
        with open(a.params, encoding="utf-8") as f:
            P.update(json.load(f))
    for s in a.set:
        k, v = s.split("=", 1)
        if k not in P:
            ap.error("ไม่มีพารามิเตอร์ชื่อ " + k)
        P[k] = type(PARAMS[k])(float(v))
    if a.dump_params:
        print(json.dumps(P, ensure_ascii=False, indent=2))
        return 0

    outdir = a.outdir or os.path.join("output", "robot_arm_" + time.strftime("%Y%m%d_%H%M%S"))
    if os.path.exists(outdir) and os.listdir(outdir):
        print("โฟลเดอร์ %s มีไฟล์อยู่แล้ว  ไม่เขียนทับ ให้ระบุ --outdir ใหม่" % outdir)
        return 2
    os.makedirs(outdir, exist_ok=True)
    logf = open(os.path.join(outdir, "build_log.txt"), "w", encoding="utf-8")

    def log(s):
        print(s)
        logf.write(s + "\n")
        logf.flush()

    parts, d, errs = build_design(P)
    if errs:
        for e in errs:
            log("ผิดพลาด: " + e)
        return 2
    report(parts, d, P, log)
    analysis = analyze(parts, d, P, log)
    export_files(parts, d, P, outdir, analysis)

    ov = find_overlaps(parts)
    log("-" * 78)
    if ov:
        log("พบชิ้นส่วนซ้อนทับกัน %d คู่ (ตรวจด้วย Python)" % len(ov))
        for n1, n2, v in ov:
            log("   %s  x  %s   %.0f mm3" % (n1, n2, v))
        if not a.force:
            log("หยุด -- แก้พารามิเตอร์ก่อน (หรือใช้ --force)")
            return 3
    else:
        log("ตรวจการชนด้วย Python: ไม่พบการซ้อนทับ (ผิวสัมผัสกันได้)")

    dry = a.dry_run
    if not dry:
        if os.name != "nt":
            log("ไม่ใช่ Windows -> ใช้ --dry-run อัตโนมัติ")
            dry = True
        else:
            try:
                import win32com.client  # noqa: F401
            except Exception:
                log("ไม่มี pywin32 (pip install pywin32) -> ใช้ --dry-run อัตโนมัติ")
                dry = True
    if dry:
        log("เสร็จ (dry-run)  ผลลัพธ์อยู่ที่ %s" % os.path.abspath(outdir))
        return 0

    sw = connect_sw()
    log("-" * 78)
    log("สร้างไฟล์ part")
    paths = {}
    for pt in parts:
        if pt.file not in paths:
            paths[pt.file] = build_part_sw(sw, pt, os.path.abspath(outdir), log)
    log("-" * 78)
    log("สร้าง assembly")
    res = build_assembly_sw(sw, parts, paths, os.path.abspath(outdir), log)
    log("เสร็จ  ผลลัพธ์อยู่ที่ %s" % os.path.abspath(outdir))
    return 0 if res else 4


if __name__ == "__main__":
    sys.exit(main())
