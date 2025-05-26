import unittest
from unittest.mock import MagicMock, patch
from ryu.controller import ofp_event
from ryu.ofproto import ofproto_v1_3
from ryu.controller.handler import set_ev_cls
from ryu.base import app_manager
from ryu.lib.packet import packet, ethernet
from ryu.ofproto import ether

class DummyDatapath:
    def __init__(self, id):
        self.id = id
        self.ofproto = ofproto_v1_3
        self.ofproto_parser = MagicMock()
        self.send_msg = MagicMock()

class DummyMsg:
    def __init__(self, datapath, data, in_port, buffer_id):
        self.datapath = datapath
        self.data = data
        self.match = MagicMock()
        self.match.__getitem__.side_effect = lambda k: in_port if k == 'in_port' else None
        self.buffer_id = buffer_id
        self.reason = None
        self.table_id = None
        self.cookie = None
        self.in_port = in_port

class CoreSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(CoreSwitch, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, 'CONFIG_DISPATCHER')
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=0, match=match, instructions=inst)
        datapath.send_msg(mod)

    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        dst = eth.dst
        src = eth.src

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        self.mac_to_port[dpid][src] = msg.in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=msg.in_port, eth_dst=dst, eth_src=src)
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
            mod = parser.OFPFlowMod(datapath=datapath, priority=1, match=match,
                                    instructions=inst, buffer_id=msg.buffer_id)
            datapath.send_msg(mod)

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, in_port=msg.in_port,
                                  actions=actions, data=msg.data)
        datapath.send_msg(out)


class TestCoreSwitch(unittest.TestCase):
    def setUp(self):
        self.controller = CoreSwitch()
        self.dp = DummyDatapath(1)

    def test_switch_features_handler(self):
        msg = MagicMock()
        msg.datapath = self.dp
        ev = MagicMock()
        ev.msg = msg

        self.controller.switch_features_handler(ev)
        self.dp.send_msg.assert_called_once()

    @patch('ryu.lib.packet.packet.Packet')
    def test_packet_in_handler_flow_add(self, mock_packet):
        src_mac = "00:00:00:00:00:01"
        dst_mac = "00:00:00:00:00:02"
        in_port = 1
        data = b"dummy_data"

        eth_mock = MagicMock()
        eth_mock.src = src_mac
        eth_mock.dst = dst_mac

        mock_pkt = MagicMock()
        mock_pkt.get_protocols.return_value = [eth_mock]
        mock_packet.return_value = mock_pkt

        msg = DummyMsg(self.dp, data, in_port, self.dp.ofproto.OFP_NO_BUFFER)
        ev = MagicMock()
        ev.msg = msg

        self.controller.mac_to_port[self.dp.id] = {dst_mac: 2}

        self.dp.ofproto_parser.OFPActionOutput.return_value = "action_forward"
        self.dp.ofproto_parser.OFPMatch.return_value = "match"
        self.dp.ofproto_parser.OFPInstructionActions.return_value = "inst"
        self.dp.ofproto_parser.OFPFlowMod.return_value = "flow_mod_msg"
        self.dp.ofproto_parser.OFPPacketOut.return_value = "packetout_forward"

        self.controller.packet_in_handler(ev)

        send_msg_calls = [call[0][0] for call in self.dp.send_msg.call_args_list]

        self.assertIn("flow_mod_msg", send_msg_calls, "FlowMod має бути надісланий для встановлення потоку")
        self.assertIn("packetout_forward", send_msg_calls, "PacketOut має бути надісланий для відправлення фрейму")

    @patch('ryu.lib.packet.packet.Packet')
    def test_packet_in_handler_flood_when_unknown_destination(self, mock_packet):
        src_mac = "00:00:00:00:00:01"
        dst_mac = "00:00:00:00:00:FF"
        in_port = 1
        data = b"dummy_data"

        eth_mock = MagicMock()
        eth_mock.src = src_mac
        eth_mock.dst = dst_mac

        mock_pkt = MagicMock()
        mock_pkt.get_protocols.return_value = [eth_mock]
        mock_packet.return_value = mock_pkt

        msg = DummyMsg(self.dp, data, in_port, self.dp.ofproto.OFP_NO_BUFFER)
        ev = MagicMock()
        ev.msg = msg

        self.controller.mac_to_port[self.dp.id] = {}

        self.dp.ofproto_parser.OFPActionOutput.return_value = "action_flood"
        self.dp.ofproto_parser.OFPPacketOut.return_value = "packetout_flood"

        self.controller.packet_in_handler(ev)

        send_msg_calls = [call[0][0] for call in self.dp.send_msg.call_args_list]
        self.assertIn("packetout_flood", send_msg_calls, "PacketOut має бути викликаний для FLOOD")


if __name__ == '__main__':
    unittest.main()
