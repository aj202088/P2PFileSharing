"""Citations:
https://www.bittorrent.org/beps/bep_0003.html BitTorrent protocol
https://bitstring.readthedocs.io/en/latest/index.html Storing bitfield information
https://stackoverflow.com/questions/7198388/accessing-bitfields-while-reading-writing-binary-data-structures Bitfield Structure
"""

from bitstring import BitArray
from protocol import *
from constants import *
import time
import random
import socket


class Peer:
    # Build Peer object
    def __init__(self, common_info, peer_info):

        # Set info from common_info
        self.k = common_info.k  # Desired nearest neighbors
        self.p = common_info.p  # Unchoking interval
        self.n = common_info.n  # Optimistic Unchoking interval
        self.file_name = common_info.file_name
        self.file_size = common_info.file_size
        self.num_pieces = common_info.num_pieces

        # Set info from peer_info
        self.peerID = peer_info.peerID
        self.host_name = peer_info.host_name
        self.listening_port = peer_info.listening_port
        self.has_file = peer_info.has_file

        # Set bitfield - all 1s if file exists, all 0s if not
        # Use bitArray to encode/decode bitfield
        self.bitfield = BitArray(self.num_pieces)

        if self.has_file:
            self.bitfield.set(1)

        self.connections = {}  # Stores all connections with Peers
        self.neighbors = {}  # Get from config/initialization
        self.unchoked_neighbors = []  # Stores unchoked neighbors/neighbors we want to exchange with
        self.neighboring_download_rates = []  # Store neighboring download rates computed over interval p

    def choke(self, peer):
        # Block neighbor from getting data
        choke_msg = build_msg(MsgType.CHOKE, None)

        # Get peer port
        port = self.connections[peer.peerID]

        # Remove neighbor from unchoked
        for neighbor in self.unchoked_neighbors:
            if neighbor == peer:
                self.unchoked_neighbors.remove(neighbor)

        # need to send message
        send_msg(port, choke_msg)

    def unchoke(self, peer):
        # Allow neighbor to get data
        unchoke_msg = build_msg(MsgType.UNCHOKE, None)

        # Get peer port
        port = self.connections[peer.peerID]

        # Add neighbor to unchoked neighbors
        self.unchoked_neighbors.append(peer)

        # need to send message
        send_msg(port, unchoke_msg)

    def compute_download_rate(self, peer):
        """TODO: Compute download rate for each neighbor"""
        download_rate = 0
        return download_rate

    def update_k_neighbors(self):
        # Run every p seconds
        """Citation: https://stackoverflow.com/questions/474528/how-to-repeatedly-execute-a-function-every-x-seconds """
        start_time = time.monotonic()
        new_k_neighbors = []
        while True:
            # Compute new neighboring download rates
            self.neighboring_download_rates.clear()
            for neighbor in self.neighbors:
                new_rate = self.compute_download_rate(neighbor)
                self.neighboring_download_rates.append(new_rate)

            # Sort from least to greatest rate
            self.neighboring_download_rates.sort()

            """TODO: Implement tie breaking logic"""

            # Get k new neighbors
            for i in range(0, self.k):
                new_k_neighbors.append(self.neighboring_download_rates[i])

            # Reset time
            time.sleep(self.p - ((time.monotonic() - start_time) % self.p))

        # Return result
        return new_k_neighbors

    def compare_bitfields(self, bitfield, peer_bitfield):
        # Compare the bitfields against each other
        # If peer bitfield has any bits that the current bitfield does not have, it is interesting
        for bit in bitfield:
            if bit == 0 and peer_bitfield.bit == 1:
                return True

        return False

    def interested(self, neighbors):
        # Check if neighbors have interesting pieces
        for neighbor in neighbors:
            if self.compare_bitfields(self, self.bitfield, neighbor.bitfield):
                # Build and send interested message
                build_msg(MsgType.INTERESTED, None)
                send_msg(neighbor.listening_port, neighbor)
            else:
                # Build and send not interested message
                build_msg(MsgType.NOT_INTERESTED, None)
                send_msg(neighbor.listening_port, neighbor)

    def exchange_pieces(self):
        return None

    def connect(self):
        return None

    def start(self):
        return None
