"""Build and audit a directed driving graph from a local OSM XML extract."""
import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import gzip
import hashlib
import heapq
import json
import math
import pathlib
import xml.etree.ElementTree as ET


SPEEDS = {"motorway": 80, "trunk": 60, "primary": 50, "secondary": 45, "tertiary": 35,
          "unclassified": 30, "residential": 30, "living_street": 10, "service": 20}
DENIED = {"no", "private", "agricultural", "forestry", "delivery", "customers"}


def tags(element):
    return {tag.get("k"): tag.get("v") for tag in element.findall("tag")}


def can_drive(properties):
    if any(key.endswith(":conditional") and key.split(":")[0] in
           ("access", "vehicle", "motor_vehicle", "motorcar", "oneway") for key in properties):
        return False
    access = next((properties[key] for key in ("motorcar", "motor_vehicle", "vehicle", "access")
                   if key in properties), "")
    return access not in DENIED


def metres(a, b):
    east = (b[0] - a[0]) * math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot(east, b[1] - a[1]) * 111195


@dataclass(frozen=True)
class Link:
    id: str
    way: str
    nodes: tuple
    length: float
    speed: float
    name: str

    @property
    def start(self):
        return self.nodes[0]

    @property
    def end(self):
        return self.nodes[-1]


def import_graph(root, origin_point, destination_point):
    coordinates, properties = {}, {}
    for node in root.findall("node"):
        identifier = node.get("id")
        coordinates[identifier] = float(node.get("lon")), float(node.get("lat"))
        properties[identifier] = tags(node)
    ways = {}
    count = Counter()
    for way in root.findall("way"):
        info = tags(way)
        road_class = info.get("highway", "").removesuffix("_link")
        if road_class not in SPEEDS or not can_drive(info):
            continue
        direction = info.get("oneway:motorcar", info.get("oneway:motor_vehicle", info.get("oneway", "")))
        if direction not in ("", "no", "0", "false", "yes", "1", "true", "-1"):
            continue
        refs = [nd.get("ref") for nd in way.findall("nd")]
        if len(refs) < 2 or set(refs).difference(coordinates):
            continue
        ways[way.get("id")] = refs, info, road_class, direction
        count.update(refs)
    restrictions = [relation for relation in root.findall("relation") if tags(relation).get("type") == "restriction"]
    keep = {ref for ref in count if count[ref] > 1 or properties[ref].get("highway") == "traffic_signals"
            or "barrier" in properties[ref]}
    keep.update(member.get("ref") for relation in restrictions for member in relation.findall("member")
                if member.get("role") == "via" and member.get("type") == "node")
    usable = {ref for ref in count if not blocked_node(properties[ref])}
    if not usable:
        raise ValueError("The extract contains no usable driving nodes")
    origin = min(usable, key=lambda ref: (metres(coordinates[ref], origin_point), ref))
    destination = min(usable, key=lambda ref: (metres(coordinates[ref], destination_point), ref))
    if origin == destination:
        raise ValueError("The two requested anchors snap to the same node")
    keep.update((origin, destination))
    links = {}
    for way, (refs, info, road_class, direction) in sorted(ways.items()):
        start = 0
        for end in range(1, len(refs)):
            if end != len(refs) - 1 and refs[end] not in keep:
                continue
            section = tuple(refs[start:end+1])
            start = end
            if blocked_node(properties[section[0]]) or blocked_node(properties[section[-1]]):
                continue
            length = sum(metres(coordinates[a], coordinates[b]) for a, b in zip(section, section[1:]))
            if not length:
                continue
            speed = info.get("maxspeed", "")
            speed = int(speed) if speed.isdecimal() and int(speed) > 0 else SPEEDS[road_class]
            one_way = direction in ("yes", "1", "true") or (
                not direction and (info.get("junction") == "roundabout" or road_class == "motorway"))
            name = info.get("name:en", info.get("name", road_class))
            if direction != "-1":
                link = Link(f"{way}:{end}:f", way, section, length, speed / 3.6, name)
                links[link.id] = link
            if not one_way:
                link = Link(f"{way}:{end}:r", way, section[::-1], length, speed / 3.6, name)
                links[link.id] = link
    return coordinates, properties, restrictions, links, origin, destination


def blocked_node(properties):
    barrier = properties.get("barrier")
    access = next((properties[key] for key in ("motorcar", "motor_vehicle", "vehicle", "access")
                   if key in properties), "")
    return not can_drive(properties) or bool(barrier and barrier != "cattle_grid" and access not in
                                            ("yes", "designated", "permissive", "destination"))


def restriction_paths(relation, by_way, outgoing):
    members = defaultdict(list)
    for member in relation.findall("member"):
        members[member.get("role")].append((member.get("type"), member.get("ref")))
    if not members["from"] or not members["to"] or not members["via"]:
        return set()
    incoming = [edge for kind, identifier in members["from"] if kind == "way" for edge in by_way[identifier]]
    destinations = {identifier for kind, identifier in members["to"] if kind == "way"}
    info = tags(relation)
    if len(members["via"]) == 1 and members["via"][0][0] == "node":
        via = members["via"][0][1]
        return {(a.id, b.id) for a in incoming if a.end == via for b in outgoing[via] if b.way in destinations
                and (info.get("restriction") != "no_u_turn" or a.start == b.end)}
    if any(kind != "way" for kind, _ in members["via"]):
        return set()
    via_ways = [identifier for _, identifier in members["via"]]
    paths = set()

    def trace(path, index):
        for edge in outgoing[path[-1].end]:
            if edge.start == path[-1].end and edge.end == path[-1].start:
                continue
            if edge in path:
                continue
            if index == len(via_ways) - 1 and edge.way in destinations:
                paths.add(tuple(item.id for item in (*path, edge)))
            if index + 1 < len(via_ways) and edge.way == via_ways[index + 1]:
                trace((*path, edge), index + 1)
            elif index >= 0 and edge.way == via_ways[index]:
                trace((*path, edge), index)

    for link in incoming:
        trace((link,), -1)
    return paths


def turn_rules(links, restrictions):
    by_way, outgoing = defaultdict(list), defaultdict(list)
    for edge in links.values():
        outgoing[edge.start].append(edge)
        by_way[edge.way].append(edge)
    forbidden = set()
    only = defaultdict(set)
    audit = []
    omitted = set()
    for relation in restrictions:
        info = tags(relation)
        if "motorcar" in info.get("except", "").replace(" ", "").split(";"):
            continue
        rule = info.get("restriction:motorcar", info.get("restriction:motor_vehicle", info.get("restriction", "")))
        paths = restriction_paths(relation, by_way, outgoing)
        if not paths or not rule.startswith(("no_", "only_")) or any("conditional" in key for key in info):
            ways = {member.get("ref") for member in relation.findall("member") if member.get("type") == "way"}
            omitted.update(edge.id for way in ways for edge in by_way[way])
            audit.append({"id": relation.get("id"), "rule": rule, "status": "excluded_member_links"})
        else:
            if rule.startswith("only_"):
                for path in paths:
                    for index in range(1, len(path)):
                        only[path[:index]].add(path[index])
            else:
                forbidden.update(paths)
            audit.append({"id": relation.get("id"), "rule": rule, "status": "mapped", "paths": len(paths)})
    return outgoing, forbidden, only, omitted, audit


def shortest_path(origin, destination, outgoing, forbidden, only, omitted):
    prefixes = {path[:i] for path in forbidden for i in range(1, len(path))} | set(only)
    longest = max(map(len, prefixes), default=0)
    frontier = [(0, origin, (), ())]
    best = {(origin, ()): 0}
    while frontier:
        cost, node, context, path = heapq.heappop(frontier)
        if cost != best[(node, context)]:
            continue
        if node == destination:
            return path
        for edge in outgoing[node]:
            if edge.id in omitted:
                continue
            if any(context[-size:] in only and edge.id not in only[context[-size:]] for size in range(1, len(context)+1)):
                continue
            trial = (*context, edge.id)
            if any(trial[-size:] in forbidden for size in range(2, len(trial)+1)):
                continue
            next_context = next((trial[-i:] for i in range(min(len(trial), longest), 0, -1)
                                 if trial[-i:] in prefixes), ())
            new_cost = cost+edge.length/edge.speed
            key = edge.end, next_context
            if new_cost < best.get(key, math.inf):
                best[key] = new_cost
                heapq.heappush(frontier, (new_cost, edge.end, next_context, (*path, edge)))
    raise ValueError("No audited driving route connects the selected anchors")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extract", type=pathlib.Path)
    parser.add_argument("--date", required=True, help="Date on which the extract was captured")
    parser.add_argument("--origin", nargs=2, type=float, default=(75.806233,26.925469), metavar=("LNG","LAT"))
    parser.add_argument("--destination", nargs=2, type=float, default=(75.8161049,26.9060159), metavar=("LNG","LAT"))
    args = parser.parse_args()
    source = args.extract.read_bytes()
    source = gzip.decompress(source) if args.extract.suffix==".gz" else source
    coordinates, properties, restrictions, links, origin, destination = import_graph(
        ET.fromstring(source), args.origin, args.destination)
    outgoing, forbidden, only, omitted, audit = turn_rules(links, restrictions)
    route = shortest_path(origin, destination, outgoing, forbidden, only, omitted)
    nodes = sorted({node for link in links.values() if link.id not in omitted for node in (link.start, link.end)})
    result = {
        "dataSource": {"name": "OpenStreetMap contributors", "license": "ODbL-1.0",
                       "captureDate": args.date, "sha256": hashlib.sha256(source).hexdigest()},
        "nodeCoordinates": {node: coordinates[node] for node in nodes},
        "mappedSignals": [node for node in nodes if properties[node].get("highway") == "traffic_signals"],
        "roads": [{"id": link.id, "osmWay": link.way, "from": link.start, "to": link.end, "length": link.length,
                   "name": link.name, "freeSpeed": link.speed, "coordinates": [coordinates[node] for node in link.nodes]}
                  for link in links.values() if link.id not in omitted],
        "forbiddenTurns": sorted(forbidden), "requiredNextLinks": [
            {"after": prefix, "allowed": sorted(edges)} for prefix, edges in sorted(only.items())],
        "restrictionAudit": audit,
        "checkedRoute": {"origin": origin, "destination": destination, "edgeIds": [edge.id for edge in route],
                         "length": round(sum(edge.length for edge in route)), "secondsAtFreeFlow": round(sum(
                             edge.length / edge.speed for edge in route)),
                         "originSnapMetres": round(metres(coordinates[origin],args.origin)),
                         "destinationSnapMetres": round(metres(coordinates[destination],args.destination))},
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
