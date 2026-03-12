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


class Peer:
    # Build Peer object
    def __init__(self, common_info, peer_info, all_peer_info, pieces):

        # Set info from common_info
        self.k = common_info[0]  # Desired nearest neighbors
        self.p = common_info[1]  # Unchoking interval
        self.n = common_info[2]  # Optimistic Unchoking interval
        self.file_name = common_info[3]
        self.file_size = common_info[4]
        self.piece_size = common_info[5]
        self.num_pieces = pieces

        # Set info from peer_info
        self.peerID = peer_info[0]
        self.host_name = peer_info[1]
        self.listening_port = peer_info[2]
        self.has_file = peer_info[3]

        # Set bitfield - all 1s if file exists, all 0s if not
        # Use bitArray to encode/decode bitfield
        self.bitfield = BitArray(self.num_pieces)

        if self.has_file:
            self.bitfield.set(1)

        # Set up neighboring information from all_peer_info
        # Include all peers except for self
        self.neighbors = {peer[0]: peer for peer in all_peer_info if
                          peer[0] != self.peerID}  # Get from config/initialization

        self.connections = {}  # Stores all connections with Peers

        self.unchoked_neighbors = []  # Stores unchoked neighbors/neighbors we want to exchange with
        self.neighboring_download_rates = []  # Store neighboring download rates computed over interval p, start with 0

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
        for i, bit in enumerate(bitfield):
            if bit == 0 and peer_bitfield[i] == 1:
                return True

        return False

    def interested(self, neighbors):
        # Check if neighbors have interesting pieces
        for neighbor in neighbors:
            if self.compare_bitfields(self.bitfield, neighbor.bitfield):
                # Build and send interested message
                send_msg(self.connections[neighbor[0]], MsgType.INTERESTED)
                send_msg(self.connections[neighbor[0]], neighbor)
            else:
                # Build and send not interested message
                send_msg(self.connections[neighbor[0]], MsgType.NOT_INTERESTED)
                send_msg(self.connections[neighbor[0]], neighbor)

    def exchange_pieces(self):
        # Get neighboring socket
        socket = self.neighbors[0].listening_port

        x = recv_message(socket, 1)
        while x.msgType != MsgType.CHOKE:

            # Check if neighbor has any bits of interest
            if self.interested(self, self.neighbors):
                # send request for bit that peer has but self doesnt
                bit = 1  # Arbitrary value
                send_msg(socket, MsgType.REQUEST, bit)

                # If piece is recieved
                if x.msgType == MsgType.PIECE:
                    # Save bit
                    # Flip bit
                    self.flip_bit(self, self.bitfield, x)

    def flip_bit(self, bitfield, bit_index):
        # Flip bit
        self.bitfield[bit_index] = 1
