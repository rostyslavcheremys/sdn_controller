import unittest
from unittest.mock import MagicMock, patch
from ryu.ofproto import ofproto_v1_3
from controller.controller  import CoreSwitch

class MockDatapath:
    def __init__(self):
        self.id = 1
        self.ofproto = ofproto_v1_3
        self.ofproto_parser = MagicMock()
        self.send_msg = MagicMock()

class MockMessage:
    def __init__(self, datapath, data, in_port, buffer_id):
        self.datapath = datapath
        self.data = data
        self.match = {'in_port': in_port}
        self.buffer_id = buffer_id

class TestCoreSwitch(unittest.TestCase):
    def setUp(self):
        self.app = CoreSwitch()
        self.datapath = MockDatapath()

    def test_handle_switch_features_installs_default_flow(self):
        msg = MagicMock()
        msg.datapath = self.datapath
        event = MagicMock()
        event.msg = msg

        self.app.handle_switch_features(event)

        self.datapath.send_msg.assert_called_once()
        print("handle_switch_features: базове flow правило встановлено")

    @patch('ryu.lib.packet.packet.Packet')
    def test_on_packet_in_known_dst_adds_flow_and_sends_packet(self, mock_packet):
        src_mac = "00:00:00:00:00:01"
        dst_mac = "00:00:00:00:00:02"
        in_port = 1
        out_port = 2
        data = b"payload"

        eth_mock = MagicMock()
        eth_mock.src = src_mac
        eth_mock.dst = dst_mac

        pkt_mock = MagicMock()
        pkt_mock.get_protocols.return_value = [eth_mock]
        mock_packet.return_value = pkt_mock

        msg = MockMessage(self.datapath, data, in_port, self.datapath.ofproto.OFP_NO_BUFFER)
        event = MagicMock()
        event.msg = msg

        self.app.mac_map[self.datapath.id] = {dst_mac: out_port}

        self.datapath.ofproto_parser.OFPActionOutput.return_value = "action"
        self.datapath.ofproto_parser.OFPMatch.return_value = "match"
        self.datapath.ofproto_parser.OFPInstructionActions.return_value = "instructions"
        self.datapath.ofproto_parser.OFPFlowMod.return_value = "flow_mod"
        self.datapath.ofproto_parser.OFPPacketOut.return_value = "packet_out"

        self.app.on_packet_in(event)

        sent_msgs = [call[0][0] for call in self.datapath.send_msg.call_args_list]
        self.assertIn("flow_mod", sent_msgs, "FlowMod не надіслано для відомого призначення")
        self.assertIn("packet_out", sent_msgs, "PacketOut не надіслано")
        self.assertIn(src_mac, self.app.mac_map[self.datapath.id])
        print("on_packet_in: додано flow і відправлено пакет для відомого MAC")

    @patch('ryu.lib.packet.packet.Packet')
    def test_on_packet_in_unknown_dst_floods(self, mock_packet):
        src_mac = "00:00:00:00:00:01"
        dst_mac = "00:00:00:00:00:FF"
        in_port = 1
        data = b"payload"

        eth_mock = MagicMock()
        eth_mock.src = src_mac
        eth_mock.dst = dst_mac

        pkt_mock = MagicMock()
        pkt_mock.get_protocols.return_value = [eth_mock]
        mock_packet.return_value = pkt_mock

        msg = MockMessage(self.datapath, data, in_port, self.datapath.ofproto.OFP_NO_BUFFER)
        event = MagicMock()
        event.msg = msg

        self.datapath.ofproto_parser.OFPActionOutput.return_value = MagicMock()
        self.datapath.ofproto_parser.OFPPacketOut.return_value = "packet_out"

        self.app.on_packet_in(event)

        sent_msgs = [call[0][0] for call in self.datapath.send_msg.call_args_list]
        has_flowmod = any("OFPFlowMod" in str(c) for c in sent_msgs)
        self.assertFalse(has_flowmod, "FlowMod не повинен бути доданий при flood")
        self.assertIn("packet_out", sent_msgs, "PacketOut повинен бути надісланий при flood")
        print("on_packet_in: невідоме призначення — виконано flood")

if __name__ == '__main__':
    unittest.main()