import unittest
import xml.etree.ElementTree as ET

from import_osm_corridor import import_graph, shortest_path, turn_rules


class CorridorImportTest(unittest.TestCase):
    def test_keeps_curve_geometry_and_respects_via_way_restriction(self):
        xml = """<osm>
          <node id="1" lon="0" lat="0"/>
          <node id="2" lon=".001" lat=".0002"/>
          <node id="3" lon=".002" lat="0"/>
          <node id="4" lon=".003" lat="0"/>
          <node id="5" lon=".004" lat="0"/>
          <node id="6" lon=".003" lat=".001"><tag k="highway" v="traffic_signals"/></node>
          <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="primary"/><tag k="oneway" v="yes"/></way>
          <way id="11"><nd ref="3"/><nd ref="4"/><tag k="highway" v="primary"/><tag k="oneway" v="yes"/></way>
          <way id="12"><nd ref="4"/><nd ref="5"/><tag k="highway" v="primary"/><tag k="oneway" v="yes"/></way>
          <way id="13"><nd ref="4"/><nd ref="6"/><nd ref="5"/><tag k="highway" v="primary"/><tag k="oneway" v="yes"/></way>
          <relation id="20">
            <member type="way" ref="10" role="from"/><member type="way" ref="11" role="via"/>
            <member type="way" ref="12" role="to"/><tag k="type" v="restriction"/><tag k="restriction" v="no_right_turn"/>
          </relation>
        </osm>"""
        _, _, restrictions, links, origin, destination = import_graph(ET.fromstring(xml), (0, 0), (.004, 0))
        self.assertEqual(links["10:2:f"].nodes, ("1","2","3"))
        self.assertNotIn("10:2:r",links)
        self.assertIn("13:1:f",links)
        outgoing, forbidden, only, omitted, _ = turn_rules(links,restrictions)
        self.assertIn(("10:2:f","11:1:f","12:1:f"),forbidden)
        first = shortest_path(origin,destination,outgoing,forbidden,only,omitted)
        self.assertEqual([link.way for link in first], ["10","11","13","13"])
        second = shortest_path("3",destination,outgoing,forbidden,only,omitted)
        self.assertEqual([link.way for link in second], ["11","12"])

    def test_separate_osm_nodes_do_not_join_a_grade_separated_crossing(self):
        xml = """<osm>
          <node id="1" lon="0" lat="0"/><node id="2" lon=".001" lat="0"/><node id="3" lon=".002" lat="0"/>
          <node id="4" lon=".001" lat="-.001"/><node id="5" lon=".001" lat="0"/><node id="6" lon=".001" lat=".001"/>
          <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="primary"/><tag k="bridge" v="yes"/></way>
          <way id="11"><nd ref="4"/><nd ref="5"/><nd ref="6"/><tag k="highway" v="secondary"/></way>
        </osm>"""
        _, _, _, links, origin, destination = import_graph(ET.fromstring(xml), (0, 0), (.001, .001))
        outgoing, forbidden, only, omitted, _ = turn_rules(links, [])
        with self.assertRaisesRegex(ValueError,"No audited driving route"):
            shortest_path(origin,destination,outgoing,forbidden,only,omitted)
