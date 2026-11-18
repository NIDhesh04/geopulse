"""Build an editable, defense-ready GeoPulse project presentation.

The deck is assembled from native PowerPoint shapes and text, using the
existing presentation as a standards-compliant OOXML template. The canonical
route map is the only raster slide asset.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "GeoPulse_Major_Project_Presentation.pptx"
OUTPUT = ROOT / "GeoPulse_Major_Project_Presentation_Professional.pptx"
ROUTE_MAP = ROOT / "geopulse" / "results" / "phase11" / "figures" / "01_end_to_end_route.png"

EMU = 914400
W, H = 13.333333, 7.5

NAVY = "10233F"
NAVY2 = "183456"
INK = "17283E"
MUTED = "5D6B7D"
TEAL = "12A995"
BLUE = "3478F6"
AMBER = "E9A23B"
CORAL = "E5675A"
GREEN = "218C65"
PALE = "F3F6FA"
PALE_BLUE = "EAF1FC"
PALE_TEAL = "E7F6F3"
PALE_AMBER = "FCF3E4"
WHITE = "FFFFFF"
LINE = "DCE3EC"
FONT = "Aptos"

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
ET.register_namespace("p", P)
ET.register_namespace("a", A)
ET.register_namespace("r", R)
ET.register_namespace("", CT)


def q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def inch(value: float) -> int:
    return round(value * EMU)


class Slide:
    def __init__(self, number: int, background: str = PALE, dark: bool = False):
        self.number = number
        self.dark = dark
        self.root = ET.Element(q(P, "sld"), {"showMasterSp": "0"})
        c_sld = ET.SubElement(self.root, q(P, "cSld"))
        self.tree = ET.SubElement(c_sld, q(P, "spTree"))
        nv = ET.SubElement(self.tree, q(P, "nvGrpSpPr"))
        ET.SubElement(nv, q(P, "cNvPr"), {"id": "1", "name": ""})
        ET.SubElement(nv, q(P, "cNvGrpSpPr"))
        ET.SubElement(nv, q(P, "nvPr"))
        grp = ET.SubElement(self.tree, q(P, "grpSpPr"))
        xfrm = ET.SubElement(grp, q(A, "xfrm"))
        ET.SubElement(xfrm, q(A, "off"), {"x": "0", "y": "0"})
        ET.SubElement(xfrm, q(A, "ext"), {"cx": "0", "cy": "0"})
        ET.SubElement(xfrm, q(A, "chOff"), {"x": "0", "y": "0"})
        ET.SubElement(xfrm, q(A, "chExt"), {"cx": "0", "cy": "0"})
        self._id = 2
        self.shape(background, 0, 0, W, H, radius=0, line=None, name="Slide background")
        self.image_relationships: list[tuple[str, str]] = []
        self.next_rel = 2

    def _nv(self, shape, name: str, kind: str = "shape"):
        nv = ET.SubElement(shape, q(P, "nvSpPr"))
        ET.SubElement(nv, q(P, "cNvPr"), {"id": str(self._id), "name": name})
        ET.SubElement(nv, q(P, "cNvSpPr"))
        ET.SubElement(nv, q(P, "nvPr"))
        self._id += 1

    @staticmethod
    def _solid(parent, color: str, alpha: int | None = None):
        fill = ET.SubElement(parent, q(A, "solidFill"))
        rgb = ET.SubElement(fill, q(A, "srgbClr"), {"val": color})
        if alpha is not None:
            ET.SubElement(rgb, q(A, "alpha"), {"val": str(alpha)})

    def shape(
        self,
        fill: str | None,
        x: float,
        y: float,
        w: float,
        h: float,
        radius: float = 0.15,
        line: str | None = None,
        line_width: float = 1,
        name: str = "Shape",
        geometry: str | None = None,
        alpha: int | None = None,
    ):
        sp = ET.SubElement(self.tree, q(P, "sp"))
        self._nv(sp, name)
        sppr = ET.SubElement(sp, q(P, "spPr"))
        xfrm = ET.SubElement(sppr, q(A, "xfrm"))
        ET.SubElement(xfrm, q(A, "off"), {"x": str(inch(x)), "y": str(inch(y))})
        ET.SubElement(xfrm, q(A, "ext"), {"cx": str(inch(w)), "cy": str(inch(h))})
        geom = geometry or ("roundRect" if radius else "rect")
        prst = ET.SubElement(sppr, q(A, "prstGeom"), {"prst": geom})
        ET.SubElement(prst, q(A, "avLst"))
        if fill:
            self._solid(sppr, fill, alpha)
        else:
            ET.SubElement(sppr, q(A, "noFill"))
        ln = ET.SubElement(sppr, q(A, "ln"), {"w": str(round(line_width * 12700))})
        if line:
            self._solid(ln, line)
        else:
            ET.SubElement(ln, q(A, "noFill"))
        return sp

    def line(self, x1: float, y1: float, x2: float, y2: float, color: str = LINE,
             width: float = 1.5, dash: str | None = None, arrow: bool = False,
             name: str = "Connector"):
        sp = ET.SubElement(self.tree, q(P, "sp"))
        self._nv(sp, name)
        sppr = ET.SubElement(sp, q(P, "spPr"))
        xfrm_attrib = {}
        if x2 < x1:
            xfrm_attrib["flipH"] = "1"
        if y2 < y1:
            xfrm_attrib["flipV"] = "1"
        xfrm = ET.SubElement(sppr, q(A, "xfrm"), xfrm_attrib)
        ET.SubElement(xfrm, q(A, "off"), {"x": str(inch(min(x1, x2))), "y": str(inch(min(y1, y2)))})
        ET.SubElement(xfrm, q(A, "ext"), {"cx": str(max(1, inch(abs(x2 - x1)))), "cy": str(max(1, inch(abs(y2 - y1))))})
        prst = ET.SubElement(sppr, q(A, "prstGeom"), {"prst": "line"})
        ET.SubElement(prst, q(A, "avLst"))
        ln = ET.SubElement(sppr, q(A, "ln"), {"w": str(round(width * 12700))})
        self._solid(ln, color)
        if dash:
            ET.SubElement(ln, q(A, "prstDash"), {"val": dash})
        if arrow:
            ET.SubElement(ln, q(A, "headEnd"), {"type": "triangle"})
        return sp

    def text(self, value: str, x: float, y: float, w: float, h: float,
             size: float = 16, color: str = INK, bold: bool = False,
             align: str = "l", valign: str = "t", font: str = FONT,
             italic: bool = False, margin: float = 0, name: str = "Text"):
        sp = ET.SubElement(self.tree, q(P, "sp"))
        self._nv(sp, name)
        sppr = ET.SubElement(sp, q(P, "spPr"))
        xfrm = ET.SubElement(sppr, q(A, "xfrm"))
        ET.SubElement(xfrm, q(A, "off"), {"x": str(inch(x)), "y": str(inch(y))})
        ET.SubElement(xfrm, q(A, "ext"), {"cx": str(inch(w)), "cy": str(inch(h))})
        geom = ET.SubElement(sppr, q(A, "prstGeom"), {"prst": "rect"})
        ET.SubElement(geom, q(A, "avLst"))
        ET.SubElement(sppr, q(A, "noFill"))
        ln = ET.SubElement(sppr, q(A, "ln"))
        ET.SubElement(ln, q(A, "noFill"))
        body = ET.SubElement(sp, q(P, "txBody"))
        ET.SubElement(body, q(A, "bodyPr"), {
            "wrap": "square", "anchor": "ctr" if valign == "ctr" else "t",
            "lIns": str(inch(margin)), "rIns": str(inch(margin)),
            "tIns": str(inch(margin)), "bIns": str(inch(margin)),
        })
        ET.SubElement(body, q(A, "lstStyle"))
        for paragraph in value.split("\n"):
            p = ET.SubElement(body, q(A, "p"))
            ET.SubElement(p, q(A, "pPr"), {"algn": {"l": "l", "c": "ctr", "r": "r"}[align]})
            if paragraph:
                run = ET.SubElement(p, q(A, "r"))
                rpr = ET.SubElement(run, q(A, "rPr"), {
                    "lang": "en-US", "sz": str(round(size * 100)),
                    "b": "1" if bold else "0", "i": "1" if italic else "0",
                })
                self._solid(rpr, color)
                ET.SubElement(rpr, q(A, "latin"), {"typeface": font})
                t = ET.SubElement(run, q(A, "t"))
                t.text = paragraph
            end = ET.SubElement(p, q(A, "endParaRPr"), {"lang": "en-US", "sz": str(round(size * 100))})
            self._solid(end, color)
            ET.SubElement(end, q(A, "latin"), {"typeface": font})
        return sp

    def dot(self, x: float, y: float, d: float, color: str, line: str | None = None, name: str = "Dot"):
        return self.shape(color, x, y, d, d, radius=0, line=line, geometry="ellipse", name=name)

    def picture(self, path: Path, x: float, y: float, box_w: float, box_h: float, name: str):
        from PIL import Image
        with Image.open(path) as image:
            iw, ih = image.size
        scale = min(box_w / iw, box_h / ih)
        w, h = iw * scale, ih * scale
        x += (box_w - w) / 2
        y += (box_h - h) / 2
        rel_id = f"rId{self.next_rel}"
        self.next_rel += 1
        media_name = f"geopulse_{name.lower().replace(' ', '_')}.png"
        self.image_relationships.append((rel_id, media_name))
        pic = ET.SubElement(self.tree, q(P, "pic"))
        nv = ET.SubElement(pic, q(P, "nvPicPr"))
        ET.SubElement(nv, q(P, "cNvPr"), {"id": str(self._id), "name": name})
        ET.SubElement(nv, q(P, "cNvPicPr"))
        ET.SubElement(nv, q(P, "nvPr"))
        self._id += 1
        blipfill = ET.SubElement(pic, q(P, "blipFill"))
        ET.SubElement(blipfill, q(A, "blip"), {q(R, "embed"): rel_id})
        stretch = ET.SubElement(blipfill, q(A, "stretch"))
        ET.SubElement(stretch, q(A, "fillRect"))
        sppr = ET.SubElement(pic, q(P, "spPr"))
        xfrm = ET.SubElement(sppr, q(A, "xfrm"))
        ET.SubElement(xfrm, q(A, "off"), {"x": str(inch(x)), "y": str(inch(y))})
        ET.SubElement(xfrm, q(A, "ext"), {"cx": str(inch(w)), "cy": str(inch(h))})
        geom = ET.SubElement(sppr, q(A, "prstGeom"), {"prst": "rect"})
        ET.SubElement(geom, q(A, "avLst"))

    def xml(self) -> bytes:
        clr = ET.SubElement(self.root, q(P, "clrMapOvr"))
        ET.SubElement(clr, q(A, "masterClrMapping"))
        return ET.tostring(self.root, encoding="UTF-8", xml_declaration=True)


def card(slide: Slide, x: float, y: float, w: float, h: float, fill: str = WHITE,
         line: str | None = LINE, radius: float = 0.14, name: str = "Card"):
    return slide.shape(fill, x, y, w, h, radius=radius, line=line, line_width=0.8, name=name)


def header(slide: Slide, section: str, title: str, subtitle: str = ""):
    slide.text(section.upper(), 0.62, 0.34, 5.8, 0.22, 9, TEAL, True, name="Section label")
    slide.text(title, 0.62, 0.68, 12.1, 0.52, 26, NAVY, True, name="Slide title")
    if subtitle:
        slide.text(subtitle, 0.64, 1.25, 12.0, 0.38, 12.3, MUTED, name="Slide subtitle")
    slide.shape(TEAL, 0.62, 1.78, 0.56, 0.045, radius=0, name="Title accent")


def footer(slide: Slide, number: int, source: str = "GEOPULSE  •  BHUBANESWAR"):
    slide.line(0.62, 7.08, 12.70, 7.08, LINE, 0.7, name="Footer rule")
    slide.text(source, 0.64, 7.14, 10.9, 0.18, 8, MUTED, name="Footer source")
    slide.text(f"{number:02d}", 12.05, 7.12, 0.55, 0.22, 9, MUTED, True, align="r", name="Page number")


def metric(slide: Slide, x: float, y: float, w: float, h: float, value: str, label: str,
           accent: str = TEAL, note: str = ""):
    card(slide, x, y, w, h)
    slide.shape(accent, x, y + 0.16, 0.055, h - 0.32, radius=0, name="Metric accent")
    slide.text(value, x + 0.22, y + 0.18, w - 0.4, 0.48, 25, NAVY, True, name="Metric value")
    slide.text(label, x + 0.22, y + 0.76, w - 0.4, 0.38, 11.5, MUTED, True, name="Metric label")
    if note:
        slide.text(note, x + 0.22, y + h - 0.45, w - 0.4, 0.27, 9.2, MUTED, name="Metric note")


def add_slide(slides: list[Slide], title: str, subtitle: str, section: str = "PROJECT", dark: bool = False) -> Slide:
    slide = Slide(len(slides) + 1, background=NAVY if dark else PALE, dark=dark)
    slides.append(slide)
    header(slide, section, title, subtitle)
    footer(slide, len(slides))
    return slide


def build_slides() -> list[Slide]:
    s: list[Slide] = []

    # 1. Cover
    a = Slide(1, NAVY, dark=True); s.append(a)
    # Subtle street-grid motif with live route highlighted.
    for i in range(5):
        x = 7.35 + i * 1.15
        a.line(x, 0.35, x + 0.35, 6.9, NAVY2, 0.7)
    for i in range(6):
        y = 0.55 + i * 1.0
        a.line(7.2, y, 12.95, y + 0.15, NAVY2, 0.7)
    network = [(7.55, 5.95), (8.2, 5.1), (9.2, 4.9), (9.7, 3.9), (10.9, 3.55), (12.2, 2.65),
               (8.7, 3.55), (9.7, 2.6), (11.5, 1.6), (12.25, 5.2)]
    for u, v in [(0,1),(1,2),(2,3),(3,4),(4,5),(1,6),(6,7),(7,8),(3,7),(2,9),(9,4),(4,8)]:
        a.line(*network[u], *network[v], "34506F", 1.15)
    route = [(7.55,5.95),(8.2,5.1),(9.2,4.9),(9.7,3.9),(10.9,3.55),(12.2,2.65)]
    for p1, p2 in zip(route, route[1:]):
        a.line(*p1, *p2, TEAL, 3.3)
    for i, (x, y) in enumerate(network):
        a.dot(x - 0.055, y - 0.055, 0.11, TEAL if i in (0, 5) else "8BA2BF")
    a.text("B.TECH MAJOR PROJECT  ·  7TH SEMESTER", 0.82, 0.83, 5.9, 0.32, 11, "8ADFD2", True)
    a.text("GeoPulse", 0.78, 1.62, 6.3, 0.95, 46, WHITE, True, font="Aptos Display")
    a.text("AI-based dynamic\ntraffic routing system", 0.84, 2.68, 6.05, 1.18, 25, WHITE, True)
    a.text("Predict traffic. Plan intelligently. Adapt while driving.", 0.86, 4.15, 5.9, 0.66, 15, "D1DCE8")
    a.shape(TEAL, 0.86, 5.05, 0.54, 0.055, radius=0)
    a.text("STUDY REGION", 0.86, 5.35, 2.0, 0.22, 9, "8ADFD2", True)
    a.text("Bhubaneswar, Odisha", 0.86, 5.68, 4.9, 0.38, 17, WHITE, True)
    card(a, 8.17, 5.4, 4.05, 1.12, "183456", "34506F", 0.16, "Headline result")
    a.text("84.9 s", 8.42, 5.58, 1.9, 0.45, 28, WHITE, True)
    a.text("saved in the canonical\nevening-peak replay", 10.2, 5.62, 1.72, 0.6, 11.2, "D1DCE8", True)
    a.text("A closed-loop prototype built on OSM, LightGBM and custom Dijkstra routing", 0.86, 6.62, 8.0, 0.28, 10, "A9B9CB")
    a.text("01", 12.05, 7.12, 0.55, 0.22, 9, "A9B9CB", True, align="r")

    # 2. Research question / contribution.
    a = add_slide(s, "From prediction to action", "The project connects a forecast to a real route decision, then checks whether traffic changed enough to act.", "RESEARCH QUESTION")
    card(a, 0.7, 2.1, 5.55, 3.86, WHITE)
    a.text("THE ROUTING GAP", 1.0, 2.42, 2.3, 0.25, 10, CORAL, True)
    a.text("A route can go stale\nafter the trip begins.", 1.0, 2.86, 4.75, 0.95, 25, NAVY, True)
    a.text("Static costs miss changing congestion. A forecast can also drift from what the driver later encounters.", 1.0, 4.05, 4.72, 0.75, 15, MUTED)
    a.shape(PALE_AMBER, 1.0, 5.18, 4.78, 0.48, radius=0.11)
    a.text("Research question", 1.18, 5.28, 1.5, 0.22, 10, NAVY, True)
    a.text("When is a mid-trip detour worth taking?", 2.42, 5.25, 3.17, 0.27, 11, NAVY, True)
    a.text("THE GEOPULSE LOOP", 6.82, 2.36, 3.2, 0.25, 10, TEAL, True)
    steps = [("01", "Predict", "next-hour speed"), ("02", "Plan", "shortest path"), ("03", "Observe", "new traffic"), ("04", "Adapt", "when worthwhile")]
    x_positions = [6.85, 8.34, 9.83, 11.32]
    for i, (num, title, desc) in enumerate(steps):
        x = x_positions[i]
        card(a, x, 2.94, 1.28, 1.46, WHITE, LINE, 0.12)
        a.dot(x + 0.15, 3.11, 0.25, TEAL if i == 3 else BLUE)
        a.text(num, x + 0.15, 3.125, 0.25, 0.19, 8, WHITE, True, align="c")
        a.text(title, x + 0.14, 3.53, 1.0, 0.3, 12, NAVY, True)
        a.text(desc, x + 0.14, 3.93, 1.06, 0.33, 9, MUTED)
        if i < 3:
            a.line(x + 1.3, 3.65, x + 1.45, 3.65, TEAL, 1.8, arrow=True)
    card(a, 6.86, 4.86, 5.73, 1.06, PALE_TEAL, None)
    a.text("REROUTE GATE", 7.12, 5.09, 1.7, 0.22, 9, GREEN, True)
    a.text("ΔT ≥ 10 s  AND  ΔT% ≥ 3%", 8.82, 5.02, 3.34, 0.38, 18, NAVY, True)
    a.text("The dual threshold filters out small, low-value route changes.", 7.12, 5.55, 4.85, 0.22, 10.5, MUTED)

    # 3. Problem framing.
    a = add_slide(s, "Why a shortest path can go stale", "The best path depends on the traffic state along the remaining trip, not only at departure.", "MOTIVATION")
    card(a, 0.72, 2.15, 5.85, 3.95, WHITE)
    a.text("ONE ROAD NETWORK  ·  TWO COST STATES", 1.02, 2.42, 4.5, 0.25, 9.5, MUTED, True)
    points = [(1.45,4.9),(2.55,4.0),(3.78,4.02),(5.5,3.15)]
    for p1,p2 in zip(points,points[1:]): a.line(*p1,*p2,"AFBAC8",4)
    alt = [(2.55,4.0),(3.3,5.1),(4.45,5.12),(5.5,3.15)]
    for p1,p2 in zip(alt,alt[1:]): a.line(*p1,*p2,TEAL,4)
    for i,(x,y) in enumerate(points):
        a.dot(x-0.12,y-0.12,0.24,BLUE if i==0 else (GREEN if i==3 else WHITE),line=BLUE if i==0 else (GREEN if i==3 else "92A2B4"))
    a.text("Start", 1.05, 5.26, 0.8, 0.22, 9, MUTED)
    a.text("Observed bottleneck", 3.75, 3.24, 1.72, 0.24, 9, CORAL, True)
    a.text("Destination", 4.72, 5.43, 1.4, 0.22, 9, MUTED)
    a.text("Initial route", 1.05, 5.78, 1.45, 0.22, 9, MUTED)
    a.line(2.16,5.89,2.66,5.89,"AFBAC8",2.4)
    a.text("Dynamic bypass", 3.0, 5.78, 1.5, 0.22, 9, MUTED)
    a.line(4.19,5.89,4.69,5.89,TEAL,2.4)
    a.text("SYSTEM OBJECTIVES", 7.03, 2.4, 2.3, 0.24, 10, TEAL, True)
    objectives = [
        ("01", "Anticipate", "Forecast speed one hour ahead for monitored road links."),
        ("02", "Route", "Find a low-travel-time path through the directed street graph."),
        ("03", "Respond", "Recompute only when observed degradation clears both gates."),
    ]
    for i,(num,title,desc) in enumerate(objectives):
        y=2.95+i*1.0
        a.dot(7.02,y+0.05,0.34,PALE_BLUE)
        a.text(num,7.02,y+0.12,0.34,0.16,8,BLUE,True,align="c")
        a.text(title,7.55,y,1.7,0.28,14,NAVY,True)
        a.text(desc,9.08,y,3.17,0.55,11.3,MUTED)

    # 4. Data and graph.
    a = add_slide(s, "A real road graph with mapped traffic", "Historical traffic observations are linked to the Bhubaneswar drive network for routing and replay.", "DATA FOUNDATION")
    metric(a,0.72,2.12,2.84,1.52,"18,260","OSM graph nodes",BLUE)
    metric(a,3.68,2.12,2.84,1.52,"46,679","directed road edges",TEAL)
    metric(a,6.64,2.12,2.84,1.52,"700","monitored traffic links",AMBER)
    metric(a,9.60,2.12,2.84,1.52,"599 + 9","dynamic map + fallback",GREEN)
    card(a,0.72,4.12,7.36,1.78,WHITE)
    a.text("TRAFFIC INPUT",0.98,4.4,2.0,0.22,9.5,TEAL,True)
    a.text("13.2 days",0.98,4.82,1.72,0.39,20,NAVY,True)
    a.text("hourly observations",0.98,5.28,1.9,0.26,10,MUTED)
    a.line(3.04,4.55,3.04,5.54,LINE,1)
    a.text("700 arterial segments",3.38,4.78,2.35,0.3,14,NAVY,True)
    a.text("Speeds, timestamps and road metadata feed the forecasting pipeline.",3.38,5.19,4.27,0.45,10.4,MUTED)
    card(a,8.37,4.12,4.07,1.78,PALE_BLUE,None)
    a.text("MAPPING NOTE",8.67,4.4,1.7,0.22,9.5,BLUE,True)
    a.text("41 validated twin groups",8.67,4.81,3.4,0.32,15,NAVY,True)
    a.text("Duplicate sensors on the same directed edge are combined. Unmapped links use static fallback speeds.",8.67,5.24,3.34,0.5,10.4,MUTED)
    a.text("Travel time is derived from length and speed; inconsistent raw travel-time fields are excluded.",0.86,6.35,11.5,0.28,10.5,MUTED,italic=True)

    # 5. Method pipeline.
    a = add_slide(s, "Method: forecast, plan, observe, adapt", "Five project stages form one forward-looking and reactive traffic-routing loop.", "SYSTEM METHOD")
    stages = [
        ("DATA", "Road + traffic", "OpenStreetMap graph\nMapped hourly speeds", BLUE),
        ("PHASE 7", "Forecast", "LightGBM\nNext-hour speeds", TEAL),
        ("PHASE 8", "Initial route", "Custom Dijkstra\nPredicted costs", AMBER),
        ("PHASE 9", "Replay trip", "Vehicle advances\nLink by link", CORAL),
        ("PHASE 10–11", "Reroute", "Observed costs\nDual-threshold gate", GREEN),
    ]
    for i,(tag,title,desc,color) in enumerate(stages):
        x=0.72+i*2.48
        card(a,x,2.7,2.15,2.05,WHITE)
        a.shape(color,x,2.7,2.15,0.07,radius=0,name=f"{title} accent")
        a.text(tag,x+0.18,3.02,1.75,0.2,8.4,color,True)
        a.text(title,x+0.18,3.42,1.8,0.34,14,NAVY,True)
        a.text(desc,x+0.18,3.95,1.8,0.58,10.5,MUTED)
        if i<4: a.line(x+2.17,3.67,x+2.42,3.67,TEAL,2,arrow=True)
    card(a,0.85,5.35,11.55,0.9,NAVY,None)
    a.text("Route cost per edge",1.15,5.62,2.0,0.25,10,"AFC1D6",True)
    a.text("wₑ = lengthₑ / (speedₑ / 3.6)",3.55,5.53,3.45,0.36,17,WHITE,True)
    a.text("seconds",7.05,5.63,0.8,0.22,10,"AFC1D6")
    a.text("R₀ at departure  →  compare at t₁  →  optional new subpath R₁",8.0,5.56,4.04,0.36,11,"D1DCE8",True)

    # 6. Prediction evaluation.
    a = add_slide(s, "Phase 7: next-hour speed prediction", "LightGBM performs well against persistence, while the historical same-hour baseline remains a strong comparator.", "PREDICTION")
    card(a,0.72,2.14,7.15,4.05,WHITE)
    a.text("TEST MAE  ·  LOWER IS BETTER",1.02,2.43,4.6,0.25,10,MUTED,True)
    values=[("Historical",0.8354,TEAL),("LightGBM",0.9340,BLUE),("Persistence",1.2101,AMBER)]
    chart_x, chart_w=2.48,4.55
    for i,(name,val,color) in enumerate(values):
        y=3.15+i*0.83
        a.text(name,1.02,y+0.07,1.3,0.28,11.3,NAVY,True)
        a.shape("E9EEF5",chart_x,y,chart_w,0.32,radius=0.08,name="Chart track")
        a.shape(color,chart_x,y,chart_w*(val/1.35),0.32,radius=0.08,name="MAE bar")
        a.text(f"{val:.3f}",chart_x+chart_w+0.12,y+0.03,0.78,0.25,11,NAVY,True)
    a.text("Speed error (km/h)",1.02,5.78,2.0,0.2,9,MUTED)
    metric(a,8.17,2.14,4.23,1.42,"0.934 km/h","LightGBM test MAE",BLUE)
    metric(a,8.17,3.78,2.0,1.38,"1.601","RMSE · km/h",TEAL)
    metric(a,10.38,3.78,2.02,1.38,"0.9679","R²",GREEN)
    a.text("30,800 test observations  ·  25 engineered features  ·  chronological split",8.25,5.62,4.15,0.45,10.2,MUTED)
    a.text("On the full test set, LightGBM improves MAE over persistence; historical same-hour lookup is slightly better.",0.92,6.47,11.4,0.3,10.5,NAVY,True)

    # 7. Routing algorithm and evaluation design.
    a = add_slide(s, "Phase 8: transparent shortest-path routing", "A scratch-built Dijkstra solver uses physical travel-time weights on a directed road graph.", "ROUTING")
    card(a,0.72,2.15,5.18,3.92,NAVY,None)
    a.text("EDGE TRAVEL-TIME COST",1.08,2.54,3.5,0.22,9,"AFC1D6",True)
    a.text("wₑ = Lₑ / (vₑ / 3.6)",1.05,3.0,4.4,0.58,27,WHITE,True)
    a.text("meters",1.08,3.75,1.0,0.22,10,"AFC1D6")
    a.text("km/h",2.72,3.75,0.8,0.22,10,"AFC1D6")
    a.line(1.07,4.25,5.44,4.25,"34506F",1)
    a.text("Min-heap Dijkstra",1.08,4.6,2.3,0.3,15,WHITE,True)
    a.text("Directed edges",1.08,5.08,1.7,0.25,11,"D1DCE8")
    a.text("Parallel links",3.15,5.08,1.7,0.25,11,"D1DCE8")
    a.text("Returns exact edge path",1.08,5.51,3.65,0.28,11,"D1DCE8")
    a.text("CONTROLLED OFFLINE EVALUATION",6.47,2.43,4.0,0.25,9.5,TEAL,True)
    sequence=[("50", "OD pairs"),("16", "timestamps"),("800", "shared cases")]
    for i,(val,label) in enumerate(sequence):
        x=6.52+i*1.87
        card(a,x,2.99,1.55,1.15,WHITE)
        a.text(val,x+0.16,3.18,1.18,0.35,20,NAVY,True,align="c")
        a.text(label,x+0.13,3.65,1.26,0.23,9,MUTED,True,align="c")
        if i<2:a.line(x+1.57,3.54,x+1.81,3.54,TEAL,1.8,arrow=True)
    card(a,6.49,4.53,5.73,1.36,PALE_BLUE,None)
    a.text("Fair comparison",6.81,4.83,1.52,0.26,12,NAVY,True)
    a.text("Each candidate route is evaluated with the same observed traffic at that time.",8.4,4.79,3.45,0.66,11,MUTED)

    # 8. Offline routing benchmark.
    a = add_slide(s, "Offline routing gains are real, but modest", "Across 800 OD-time cases, prediction-guided routes approach the current-traffic oracle.", "RESULTS  ·  PHASE 8")
    card(a,0.72,2.12,7.5,4.18,WHITE)
    a.text("MEAN JOURNEY TIME  ·  LOWER IS BETTER",1.05,2.43,4.4,0.24,9.5,MUTED,True)
    a.text("Scale: 1,058–1,068 seconds",5.19,2.43,2.57,0.24,9,MUTED,align="r")
    vals=[("Static",1066.81,NAVY2),("Historical",1063.10,TEAL),("LightGBM",1063.08,BLUE),("Current oracle",1060.75,GREEN)]
    left, width=2.05, 4.75
    for i,(label,val,color) in enumerate(vals):
        y=3.0+i*0.65
        a.text(label,1.05,y+0.07,1.05,0.25,10.5,NAVY,True)
        a.shape("E9EEF5",left,y,width,0.28,radius=0.06,name="Time scale")
        bar=(val-1058)/10*width
        a.shape(color,left,y,max(0.1,bar),0.28,radius=0.06,name="Mean travel-time bar")
        a.text(f"{val:,.2f} s",6.92,y+0.04,0.96,0.22,10,NAVY,True,align="r")
    a.text("Static baseline",2.02,5.83,1.2,0.2,8.7,MUTED)
    a.text("1,058 s",6.48,5.83,0.75,0.2,8.7,MUTED,align="r")
    metric(a,8.55,2.12,3.82,1.42,"3.73 s","LightGBM mean saving vs static",BLUE)
    metric(a,8.55,3.78,3.82,1.42,"2.33 s","mean regret vs current oracle",GREEN)
    a.text("Historical and LightGBM mean journey times differ by 0.02 s (paired test p = 0.8533).",8.66,5.52,3.55,0.56,10.1,MUTED)
    a.text("Offline prediction helps route choice; its biggest value appears during congested periods and in the later reactive loop.",0.92,6.5,11.6,0.3,10.2,NAVY,True)

    # 9. Canonical event sequence.
    a = add_slide(s, "Phase 9: one trip, one traffic surprise", "The canonical evening-peak replay shows how an observation changes the remaining-route decision.", "DYNAMIC ROUTING")
    timeline=[
        ("19:30", "PREDICT", "Cloud forecasts\nnext-hour speeds", BLUE),
        ("DEPART", "PLAN R₀", "74 links\n10.98 km", TEAL),
        ("20:30", "OBSERVE", "31.7 → 14.0\nkm/h bottleneck", CORAL),
        ("20.3%", "COMPARE", "ΔT = 84.9 s\nΔT% = 9.23%", AMBER),
        ("REROUTE", "PLAN R₁", "46 links\nnew bypass", GREEN),
    ]
    for i,(time,title,desc,color) in enumerate(timeline):
        x=0.78+i*2.49
        a.dot(x+0.66,2.75,0.43,color)
        a.text(str(i+1),x+0.66,2.86,0.43,0.18,9,WHITE,True,align="c")
        if i<4:a.line(x+1.1,2.97,x+2.45,2.97,LINE,2)
        a.text(time,x+0.03,3.42,1.7,0.22,9.5,color,True,align="c")
        a.text(title,x-0.05,3.8,1.86,0.31,13,NAVY,True,align="c")
        a.text(desc,x-0.14,4.25,2.03,0.6,10.2,MUTED,align="c")
    card(a,0.83,5.44,11.62,0.77,PALE_TEAL,None)
    a.text("Gate satisfied",1.08,5.69,1.45,0.23,10,GREEN,True)
    a.text("84.9 s ≥ 10 s",3.0,5.65,1.76,0.3,15,NAVY,True)
    a.text("AND",5.05,5.69,0.55,0.22,9,MUTED,True,align="c")
    a.text("9.23% ≥ 3%",6.0,5.65,1.75,0.3,15,NAVY,True)
    a.text("→ issue route update",8.55,5.67,2.65,0.28,12,GREEN,True)

    # 10. Route map and canonical outcome.
    a = add_slide(s, "A bypass recovers 84.9 seconds", "Khandagiri Square → Rasulgarh Square  ·  10.98 km  ·  evening peak", "CANONICAL DEMONSTRATION")
    card(a,0.72,2.13,7.32,4.43,WHITE)
    a.picture(ROUTE_MAP,0.9,2.2,6.96,4.27,"Route map")
    a.text("Blue: traversed  ·  Red: abandoned congested corridor  ·  Green: dynamic bypass",1.03,6.26,6.7,0.2,8.3,MUTED,align="c")
    card(a,8.36,2.13,4.01,4.43,WHITE)
    a.text("NO REROUTE",8.7,2.52,1.7,0.22,9,CORAL,True)
    a.text("21.45 min",8.7,2.88,2.95,0.45,24,NAVY,True)
    a.shape("E9EEF5",8.72,3.48,3.15,0.22,radius=0.06,name="Baseline duration track")
    a.shape(CORAL,8.72,3.48,3.15,0.22,radius=0.06,name="Baseline duration")
    a.text("WITH GEOPULSE",8.7,4.08,2.3,0.22,9,GREEN,True)
    a.text("20.04 min",8.7,4.42,2.95,0.45,24,NAVY,True)
    a.shape("E9EEF5",8.72,5.02,3.15,0.22,radius=0.06,name="Reroute duration track")
    a.shape(GREEN,8.72,5.02,2.94,0.22,radius=0.06,name="Reroute duration")
    a.text("−1.42 min  ·  6.60% faster",8.7,5.5,3.2,0.34,12,GREEN,True)
    a.text("Replay result, single canonical journey",8.7,6.05,3.25,0.24,9.5,MUTED)

    # 11. Rerouting policy benchmark.
    a = add_slide(s, "The dual gate reroutes selectively", "A 20-journey replay benchmark measured when to switch paths and when to stay put.", "POLICY EVALUATION  ·  PHASE 10")
    metric(a,0.75,2.16,2.75,1.56,"8 / 20","reroutes triggered",TEAL)
    metric(a,3.64,2.16,2.75,1.56,"12 / 20","reroutes suppressed",BLUE)
    metric(a,6.53,2.16,2.75,1.56,"100%","triggered cases beneficial",GREEN)
    metric(a,9.42,2.16,2.75,1.56,"0%","triggered cases detrimental",AMBER)
    card(a,0.75,4.14,5.48,1.82,WHITE)
    a.text("WHEN THE GATE FIRES",1.05,4.47,2.35,0.22,9.5,TEAL,True)
    a.text("84.91 s",1.05,4.86,1.65,0.4,22,NAVY,True)
    a.text("mean saving per triggered journey",2.68,4.91,3.1,0.32,10.5,MUTED)
    a.text("Across all 20 replays",1.05,5.48,2.0,0.24,10,MUTED,True)
    a.text("33.96 s mean saving per journey",3.0,5.45,2.85,0.28,11,NAVY,True)
    card(a,6.62,4.14,5.55,1.82,PALE_BLUE,None)
    a.text("WHY NOT ALWAYS REROUTE?",6.93,4.47,2.9,0.22,9.5,BLUE,True)
    a.text("The 10 s + 3% gate captures 96.3% of always-reroute savings while reducing route changes by 20%.",6.93,4.9,4.72,0.65,13,NAVY,True)
    a.text("Results describe this 20-trip replay set; they are not a universal fleet guarantee.",0.92,6.45,11.6,0.25,10,MUTED,italic=True)

    # 12. Architecture.
    a = add_slide(s, "Phase 11: integrated edge–cloud prototype", "The system separates model forecasting, regional route decisions and in-vehicle trip simulation.", "INTEGRATED SYSTEM")
    tiers=[
        ("CLOUD", "Model service", "Historical traffic  ·  25 features\nLightGBM next-hour speed forecast", BLUE, PALE_BLUE),
        ("EDGE", "Regional route service", "Sensor update  ·  dynamic edge weights\nDijkstra  ·  dual-threshold decision", AMBER, PALE_AMBER),
        ("VEHICLE", "Trip simulator", "Link-by-link movement  ·  position telemetry\nReceives and applies route updates", GREEN, PALE_TEAL),
    ]
    yvals=[2.25,3.65,5.05]
    for i,(label,title,body,color,fill) in enumerate(tiers):
        y=yvals[i]
        card(a,1.08,y,11.15,1.05,fill,None)
        a.shape(color,1.08,y,0.09,1.05,radius=0,name=f"{label} tier accent")
        a.text(label,1.42,y+0.17,1.35,0.2,9,color,True)
        a.text(title,1.42,y+0.47,2.72,0.32,15,NAVY,True)
        a.text(body,4.48,y+0.26,4.15,0.54,11,MUTED)
        if i==0: a.line(9.16,y+0.52,10.73,y+0.52,BLUE,2,arrow=True)
        elif i==1: a.line(9.16,y+0.52,10.73,y+0.52,AMBER,2,arrow=True)
        a.text("MODEL_UPDATE" if i==0 else ("ROUTE_UPDATE" if i==1 else "POSITION_UPDATE"),10.92,y+0.38,1.15,0.25,8.1,color,True,align="c")
    # feedback annotation
    a.line(12.52,6.1,12.52,2.98,TEAL,1.8,arrow=True)
    a.text("traffic + position feedback",10.72,6.42,1.8,0.22,8.5,TEAL,True,align="r")
    a.text("Architecture tiers are simulated as modular software on one host; no physical edge hardware was deployed.",0.94,6.62,10.9,0.2,9.5,MUTED,italic=True)

    # 13. Runtime measurements.
    a = add_slide(s, "Prototype decisions complete in milliseconds", "Measured software runtimes characterize the local prototype on the development host.", "EXECUTION PROFILE")
    card(a,0.72,2.12,7.32,4.34,WHITE)
    a.text("OPERATION",1.0,2.4,2.25,0.23,9.5,MUTED,True)
    a.text("TIME",6.78,2.4,0.78,0.23,9.5,MUTED,True,align="r")
    runtimes=[
        ("Initial Dijkstra route",60.305,BLUE),
        ("Detour Dijkstra",20.327,TEAL),
        ("Total edge reroute decision",20.391,GREEN),
        ("Dynamic weight synthesis",12.653,AMBER),
        ("Sensor telemetry ingest",9.021,CORAL),
        ("Cloud prediction broadcast",1.033,NAVY2),
    ]
    for i,(label,val,color) in enumerate(runtimes):
        y=2.9+i*0.52
        a.text(label,1.0,y+0.02,2.45,0.25,10.1,NAVY,True)
        a.shape("E9EEF5",3.52,y+0.03,2.8,0.22,radius=0.06,name="Runtime scale")
        a.shape(color,3.52,y+0.03,2.8*val/65.0,0.22,radius=0.06,name="Runtime bar")
        a.text(f"{val:.3f} ms",6.53,y+0.01,1.0,0.24,9.6,NAVY,True,align="r")
    card(a,8.4,2.12,3.98,1.52,PALE_TEAL,None)
    a.text("20.391 ms",8.74,2.43,3.22,0.46,26,GREEN,True)
    a.text("total edge reroute decision",8.75,3.05,3.1,0.25,10.5,NAVY,True)
    card(a,8.4,3.88,3.98,1.34,PALE_AMBER,None)
    a.text("60.305 ms",8.74,4.16,2.96,0.4,22,AMBER,True)
    a.text("initial 18k-node route search",8.75,4.68,3.15,0.23,10,MUTED)
    a.text("These are software execution times measured on the host. Network delay and embedded-hardware latency were not measured.",8.53,5.62,3.75,0.58,10,MUTED)

    # 14. Research integrity.
    a = add_slide(s, "Evaluation designed to prevent leakage", "Route selection and route evaluation use different traffic information at the decision boundary.", "EXPERIMENT DESIGN")
    card(a,0.75,2.22,5.72,3.86,WHITE)
    a.text("BEFORE DEPARTURE  ·  t₀",1.08,2.58,3.1,0.23,9.5,BLUE,True)
    a.text("Build initial route R₀",1.08,3.04,3.8,0.34,17,NAVY,True)
    a.text("Uses only historical and current features available for the next-hour forecast.",1.08,3.56,4.75,0.62,12,MUTED)
    a.shape(PALE_BLUE,1.08,4.55,4.86,0.83,radius=0.12)
    a.text("t₁ observations are held back",1.31,4.82,4.4,0.26,13,BLUE,True)
    a.text("No future speed enters the departure route.",1.08,5.61,4.88,0.25,10,MUTED)
    card(a,6.77,2.22,5.65,3.86,WHITE)
    a.text("AFTER TELEMETRY  ·  t₁",7.1,2.58,3.2,0.23,9.5,GREEN,True)
    a.text("Evaluate R₀ and candidate R₁",7.1,3.04,4.7,0.34,17,NAVY,True)
    a.text("Compare both using the same observed traffic state; replan only if the measured gain clears both thresholds.",7.1,3.56,4.75,0.75,12,MUTED)
    a.shape(PALE_TEAL,7.1,4.55,4.8,0.83,radius=0.12)
    a.text("ΔT ≥ 10 s  AND  ΔT% ≥ 3%",7.31,4.82,4.36,0.26,13,GREEN,True)
    a.text("Travel time is computed from physical length and speed.",7.1,5.61,4.88,0.25,10,MUTED)

    # 15. Limits and next steps.
    a = add_slide(s, "What the prototype does and does not establish", "The study demonstrates the routing loop in replay; production performance needs deployment evidence.", "SCOPE & NEXT STEPS")
    card(a,0.76,2.18,5.62,3.99,WHITE)
    a.text("CURRENT SCOPE",1.08,2.5,2.2,0.23,9.5,TEAL,True)
    current=[
        "Hourly traffic observations",
        "Single-vehicle replay",
        "Unmapped links use static fallback speeds",
        "Logical cloud–edge split on one host",
    ]
    for i,line in enumerate(current):
        y=3.02+i*0.66
        a.dot(1.1,y+0.05,0.16,TEAL)
        a.text(line,1.43,y,4.38,0.34,12,NAVY,True)
    a.text("No field network or embedded edge hardware was measured.",1.1,5.79,4.85,0.24,10.2,MUTED,italic=True)
    card(a,6.75,2.18,5.62,3.99,PALE_BLUE,None)
    a.text("NEXT ENGINEERING STEPS",7.07,2.5,3.2,0.23,9.5,BLUE,True)
    next_steps=[
        "Increase telemetry cadence to minutes",
        "Measure latency on edge hardware and network",
        "Replay larger scenario and fleet sets",
        "Model queues, signals and spillback",
    ]
    for i,line in enumerate(next_steps):
        y=3.02+i*0.66
        a.dot(7.09,y+0.05,0.16,BLUE)
        a.text(line,7.42,y,4.38,0.34,12,NAVY,True)
    a.text("Prediction quality, route choice and field effectiveness are separate measures.",7.09,5.79,4.86,0.24,10.2,MUTED,italic=True)

    # 16. Closing.
    a = Slide(16,NAVY,dark=True); s.append(a)
    a.text("CONCLUSION",0.83,0.76,2.1,0.26,10,"8ADFD2",True)
    a.text("GeoPulse is strongest\nas a closed loop.",0.82,1.33,7.2,1.25,35,WHITE,True,font="Aptos Display")
    a.text("A forecast helps choose the first route. Fresh traffic observations help decide whether that route still makes sense.",0.88,2.92,6.3,0.82,16,"D1DCE8")
    conclusions=[
        ("84.9 s", "saved on the canonical journey", TEAL),
        ("33.96 s", "mean saving across 20 replays", BLUE),
        ("10 s + 3%", "dual threshold for a reroute", AMBER),
    ]
    for i,(val,label,color) in enumerate(conclusions):
        x=0.88+i*2.4
        a.shape("183456",x,4.4,2.17,1.04,radius=0.13,line="34506F",line_width=0.8,name="Conclusion metric card")
        a.text(val,x+0.16,4.59,1.85,0.34,18,color,True,align="c")
        a.text(label,x+0.13,5.02,1.91,0.24,8.8,"D1DCE8",align="c")
    a.text("Thank you",8.6,4.2,3.2,0.62,27,WHITE,True,align="c")
    a.text("Questions?",8.6,4.93,3.2,0.36,16,"8ADFD2",True,align="c")
    a.line(8.9,5.68,11.55,5.68,"34506F",1)
    a.text("Evidence: Phase 7 metrics · Phase 10 ablation · Phase 11 demo",0.88,6.66,8.1,0.25,9,"A9B9CB")
    a.text("16",12.05,7.12,0.55,0.22,9,"A9B9CB",True,align="r")
    return s


def relationship_xml(slide: Slide) -> bytes:
    root = ET.Element(q(PR, "Relationships"))
    ET.SubElement(root, q(PR, "Relationship"), {
        "Id": "rId1", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout",
        "Target": "../slideLayouts/slideLayout1.xml",
    })
    for rel_id, media_name in slide.image_relationships:
        ET.SubElement(root, q(PR, "Relationship"), {
            "Id": rel_id, "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
            "Target": f"../media/{media_name}",
        })
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def update_content_types(data: bytes) -> bytes:
    root = ET.fromstring(data)
    exists = any(el.attrib.get("Extension", "").lower() == "png" for el in root.findall(q(CT, "Default")))
    if not exists:
        ET.SubElement(root, q(CT, "Default"), {"Extension": "png", "ContentType": "image/png"})
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def update_core_properties(data: bytes) -> bytes:
    ns_dc = "http://purl.org/dc/elements/1.1/"
    root = ET.fromstring(data)
    title = root.find(q(ns_dc, "title"))
    if title is None:
        title = ET.SubElement(root, q(ns_dc, "title"))
    title.text = "GeoPulse: AI-Based Dynamic Traffic Routing System"
    subject = root.find(q(ns_dc, "subject"))
    if subject is None:
        subject = ET.SubElement(root, q(ns_dc, "subject"))
    subject.text = "B.Tech Major Project Presentation"
    creator = root.find(q(ns_dc, "creator"))
    if creator is not None:
        creator.text = "GeoPulse Project"
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def main() -> None:
    slides = build_slides()
    replacements: dict[str, bytes] = {}
    media: dict[str, bytes] = {}
    for index, slide in enumerate(slides, start=1):
        slide_path = f"ppt/slides/slide{index}.xml"
        rel_path = f"ppt/slides/_rels/slide{index}.xml.rels"
        replacements[slide_path] = slide.xml()
        replacements[rel_path] = relationship_xml(slide)
        for _rel_id, media_name in slide.image_relationships:
            media[f"ppt/media/{media_name}"] = ROUTE_MAP.read_bytes()

    with ZipFile(TEMPLATE, "r") as source, ZipFile(OUTPUT, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            if item.filename in replacements:
                payload = replacements.pop(item.filename)
            elif item.filename == "[Content_Types].xml":
                payload = update_content_types(source.read(item.filename))
            elif item.filename == "docProps/core.xml":
                payload = update_core_properties(source.read(item.filename))
            elif item.filename in media:
                payload = media[item.filename]
                media.pop(item.filename)
            else:
                payload = source.read(item.filename)
            target.writestr(item, payload)
        for filename, payload in replacements.items():
            target.writestr(filename, payload, compress_type=ZIP_DEFLATED)
        for filename, payload in media.items():
            target.writestr(filename, payload, compress_type=ZIP_DEFLATED)

    print(f"Created {OUTPUT}")
    print(f"Slides: {len(slides)}")


if __name__ == "__main__":
    main()
