from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet

class CoreSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(CoreSwitch, self).__init__(*args, **kwargs)
        self.mac_map = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def handle_switch_features(self, event):
        datapath = event.msg.datapath
        proto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(proto.OFPP_CONTROLLER, proto.OFPCML_NO_BUFFER)]
        instructions = [parser.OFPInstructionActions(proto.OFPIT_APPLY_ACTIONS, actions)]
        flow = parser.OFPFlowMod(
            datapath=datapath, priority=0, match=match,
            instructions=instructions
        )
        datapath.send_msg(flow)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def on_packet_in(self, event):
        msg = event.msg
        datapath = msg.datapath
        proto = datapath.ofproto
        parser = datapath.ofproto_parser

        frame = packet.Packet(msg.data)
        eth = frame.get_protocols(ethernet.ethernet)[0]
        src_mac = eth.src
        dst_mac = eth.dst
        dpid = datapath.id
        in_port = msg.match['in_port']

        self.mac_map.setdefault(dpid, {})
        self.mac_map[dpid][src_mac] = in_port

        output_port = self.mac_map[dpid].get(dst_mac, proto.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(output_port)]

        if output_port != proto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_src=src_mac, eth_dst=dst_mac)
            instructions = [parser.OFPInstructionActions(proto.OFPIT_APPLY_ACTIONS, actions)]
            flow = parser.OFPFlowMod(
                datapath=datapath, priority=1,
                match=match, instructions=instructions,
                buffer_id=msg.buffer_id
            )
            datapath.send_msg(flow)

        out_packet = parser.OFPPacketOut(
            datapath=datapath, buffer_id=msg.buffer_id,
            in_port=in_port, actions=actions, data=msg.data
        )
        datapath.send_msg(out_packet)