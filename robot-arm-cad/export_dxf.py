"""
export_dxf.py -- ส่งออกแบบ 2 มิติ (DXF: ด้านหน้า/ด้านข้าง/ด้านบน + ขนาดหลัก) จากพารามิเตอร์ของ build_robot_arm.py
เปิดใน AutoCAD ได้ (Save As เป็น DWG ได้เอง)   ต้องติดตั้ง:  pip install ezdxf
    python export_dxf.py [--out output/robot_arm_layout_2D.dxf] [--set L1=600]
"""
import argparse, os, sys, math
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_robot_arm as b
import ezdxf
from ezdxf import colors

ap = argparse.ArgumentParser()
ap.add_argument("--out", default=os.path.join("output", "robot_arm_layout_2D.dxf"))
ap.add_argument("--set", action="append", default=[], metavar="ชื่อ=ค่า")
args = ap.parse_args()
P = dict(b.PARAMS)
for _s in args.set:
    _k, _v = _s.split("=", 1)
    P[_k] = type(b.PARAMS[_k])(float(_v))
parts, d, errs = b.build_design(P); assert not errs
by = dict((p.name, p) for p in parts)

doc = ezdxf.new("R2018", setup=True)
doc.units = ezdxf.units.MM
msp = doc.modelspace()

LAYERS = {  # ชื่อ layer: (สีเส้น ACI, สีเติม RGB)
    "FRAME":      (7,  (205, 210, 218)),
    "COLUMN_RAIL":(8,  (150, 158, 170)),
    "CARRIAGE":   (5,  (176, 190, 214)),
    "ARM":        (3,  (190, 214, 190)),
    "PURCHASED":  (250,(70, 78, 92)),
    "BEARING":    (9,  (160, 168, 178)),
    "GRIPPER":    (30, (240, 160, 60)),
    "DIM":        (1,  None),
    "TEXT":       (2,  None),
    "CENTER":     (4,  None),
    "TITLE":      (7,  None),
}
for n, (c, _) in LAYERS.items():
    doc.layers.add(n, color=c)
doc.layers.get("CENTER").dxf.linetype = "DASHDOT" if "DASHDOT" in doc.linetypes else "CONTINUOUS"

def layer_of(pt):
    n = pt.name
    if n.startswith(("frame", "foot", "column_base")): return "FRAME"
    if n.startswith(("column", "rail", "rack")): return "COLUMN_RAIL"
    if n.startswith(("carriage", "platform", "blk", "pinion", "a1_shaft")): return "CARRIAGE"
    if n.startswith("link"): return "ARM"
    if "bearing" in n or "hub" in n: return "BEARING"
    if n.startswith(("gripper", "finger")): return "GRIPPER"
    return "PURCHASED"

# มุมมอง: ฟังก์ชันแปลงพิกัดโลก (x,y,z)->(แกนนอน,แกนตั้ง)  และความลึก (ใกล้ผู้ดู = มาก)
VIEWS = {
    "FRONT": dict(h=lambda c: c[0],  v=lambda c: c[1],  depth=lambda c: c[2], axis="Z", org=(0, 0)),
    "SIDE":  dict(h=lambda c: c[2],  v=lambda c: c[1],  depth=lambda c: c[0], axis="X", org=(700, 0)),
    "TOP":   dict(h=lambda c: c[0],  v=lambda c: -c[2], depth=lambda c: c[1], axis="Y", org=(0, -300)),
}

def draw_part(view, pt):
    V = VIEWS[view]; ox, oy = V["org"]; ly = layer_of(pt); line_c, fill = LAYERS[ly]
    mn, mx = pt.aabb()
    def pos(c): return (ox + V["h"](c), oy + V["v"](c))
    ax = V["axis"]
    is_cyl_end = (pt.kind == "cyl" and pt.geo["axis"] == ax)
    if is_cyl_end:
        cx, cy = pos(pt.center); r = pt.geo["dia"] / 2.0
        h = msp.add_hatch(dxfattribs={"layer": ly}); h.rgb = colors.RGB(*fill)
        h.paths.add_edge_path().add_arc((cx, cy), r, 0, 360)
        msp.add_circle((cx, cy), r, dxfattribs={"layer": ly})
        return
    xs = [V["h"](mn), V["h"](mx)]
    ys = [V["v"](mn), V["v"](mx)]
    x0, x1 = ox + min(xs), ox + max(xs); y0, y1 = oy + min(ys), oy + max(ys)
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    h = msp.add_hatch(dxfattribs={"layer": ly}); h.rgb = colors.RGB(*fill)
    h.paths.add_polyline_path(pts, is_closed=True)
    msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": ly})

for view, V in VIEWS.items():
    # วาดจากไกลมาใกล้ เพื่อให้ชิ้นที่อยู่หน้าบังชิ้นหลัง
    for pt in sorted(parts, key=lambda p: V["depth"](p.center)):
        draw_part(view, pt)

# ---------- ขนาด ----------
def dim(p1, p2, base, angle=0, text=None):
    dm = msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=angle, text=text or "<>",
                            dimstyle="EZDXF", override={"dimtxt": 28, "dimasz": 26, "dimexe": 14, "dimexo": 8,
                                                        "dimgap": 8, "dimlfac": 1.0, "dimdec": 0, "dimclrt": 1, "dimclrd": 1, "dimclre": 1},
                            dxfattribs={"layer": "DIM"})
    dm.render()

def label(x, y, s, h=30, layer="TEXT", align="MIDDLE_CENTER"):
    t = msp.add_text(s, height=h, dxfattribs={"layer": layer})
    t.set_placement((x, y), align=ezdxf.enums.TextEntityAlignment[align])

ys_all = [p.aabb() for p in parts]
ymax = max(m[1][1] for m in ys_all); zmax = max(m[1][2] for m in ys_all)
bw, bd = P["base_w"], P["base_d"]
A2z = by["a2_bearing"].center[2]; A3z = by["a3_bearing"].center[2]; A4z = by["gripper_body"].center[2]
yc = d["yc"]
sx = VIEWS["SIDE"]["org"][0]

# Front
dim((-bw/2, 0), (bw/2, 0), base=(0, -90))                                   # ความกว้างฐาน 450
dim((bw/2 + 60, 0), (bw/2 + 60, ymax), base=(bw/2 + 160, 0), angle=90)      # ความสูงรวม
# Side
dim((sx + 0, 0), (sx + A2z, 0), base=(0, -90), text="<>")                  # เสา -> A2
dim((sx + A2z, 0), (sx + A3z, 0), base=(0, -150))                           # L1
dim((sx + A3z, 0), (sx + A4z, 0), base=(0, -150))                           # L2
dim((sx + 0, 0), (sx + A4z, 0), base=(0, -230), text="<>")                  # ระยะถึง A4 (ระยะเอื้อมจากหน้าเสา)
dim((sx - 120, yc - P["stroke"]/2), (sx - 120, yc + P["stroke"]/2), base=(sx - 200, 0), angle=90, text="Z stroke %d" % P["stroke"])
dim((sx - 330, 0), (sx - 330, ymax), base=(sx - 380, 0), angle=90)         # ความสูง
# Top
oy = VIEWS["TOP"]["org"][1]
dim((-bw/2, oy - bd - 20), (bw/2, oy - bd - 20), base=(0, oy - bd - 120))
dim((bw/2 + 60, oy + 40), (bw/2 + 60, oy - bd + 40), base=(bw/2 + 160, oy), angle=90, text="<>")

# เส้นศูนย์กลางข้อ + ป้ายชื่อ
for nm, z in (("A2", A2z), ("A3", A3z), ("A4", A4z)):
    msp.add_line((sx + z, -20), (sx + z, ymax + 40), dxfattribs={"layer": "CENTER"})
    label(sx + z, ymax + 80, nm, 40)
label(sx - 20, yc + 150, "A1 (Z)", 40, align="MIDDLE_RIGHT")
label(0, ymax + 120, "FRONT VIEW", 50); label(sx + 600, ymax + 120, "SIDE VIEW", 50); label(0, oy + 100, "TOP VIEW", 50)

# ---------- ตารางชื่อแบบ ----------
tx, ty = 900, -700
w, h = 900, 420
msp.add_lwpolyline([(tx, ty), (tx + w, ty), (tx + w, ty - h), (tx, ty - h)], close=True, dxfattribs={"layer": "TITLE"})
rows = [("4-AXIS ROBOT ARM - 2D LAYOUT", 40),
        ("A1 Z-axis rack & pinion | A2, A3 rotary | A4 wrist | gripper", 26),
        ("Column 4080 H1500 | Link1 8020 L550 | Link2 4040 L450", 26),
        ("Overall W%d x H%d x reach %d mm | approx. %.0f kg" % (bw, ymax, zmax + 40,
                                                              sum(p.mass_kg() for p in parts)), 26),
        ("Units: mm | Layout (concept) - purchased parts are placeholders", 22),
        ("Generated from build_robot_arm.py parameters | not for fabrication", 22)]
yy = ty - 50
for s, hh in rows:
    t = msp.add_text(s, height=hh, dxfattribs={"layer": "TITLE"}); t.set_placement((tx + 25, yy)); yy -= hh * 1.9

if os.path.exists(args.out):
    sys.exit("ไฟล์ %s มีอยู่แล้ว ไม่เขียนทับ ใช้ --out ชื่อใหม่" % args.out)
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
doc.saveas(args.out)
print("saved; parts", len(parts))
