"""Citations:
https://www.bittorrent.org/beps/bep_0003.html BitTorrent protocol
https://bitstring.readthedocs.io/en/latest/index.html Storing bitfield information
https://stackoverflow.com/questions/7198388/accessing-bitfields-while-reading-writing-binary-data-structures Bitfield Structure
"""

from bitstring import BitArray
from protocol import *
from constants import *
import random
from datetime import datetime
import threading

_log_locks = {}
_log_locks_lock = threading.Lock()

def get_log_lock(peer_id):
    with _log_locks_lock:
        if peer_id not in _log_locks:
            _log_locks[peer_id] = threading.Lock()
        return _log_locks[peer_id]

class Peer:
    # Build Peer object
    def __init__(self, common_info, peer_info, all_peer_info, pieces, connection_map, connections_lock):

        # Set info from common_info
        self.k = common_info[0]  # Desired nearest neighbors
        self.p = common_info[1]  # Unchoking interval
        self.m = common_info[2]  # Optimistic Unchoking interval
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

        self.connections_map = connection_map  # Stores all connections with Peers
        self.connections_lock = connections_lock  # Protects connections

        self.unchoked_neighbors = []  # Stores unchoked neighbors/neighbors we want to exchange with

        self.download_counter = {}   # used to store neighboring download rates
        self.download_counter_lock = threading.Lock()   # Protects download counter

        self.optimistic_neighbor = None
        self.optimistic_lock = threading.Lock()

    def start_intervals(self, p, m):
        """SOURCE: https://www.tutorialspoint.com/python/python_thread_scheduling.htm"""
        # Create timer threads
        t1 = threading.Timer(self.p, self.choose_new_neighbors_loop)
        t2 = threading.Timer(self.m, self.optimistic_unchoking_loop)
        t1.daemon = True
        t2.daemon = True
        # Start threads
        t1.start()
        t2.start()

    def optimistic_unchoking_loop(self):
        # Call function
        self.optimistic_unchoke()
        # Reset timer
        t = threading.Timer(self.m, self.optimistic_unchoking_loop)
        t.daemon = True
        t.start()

    def choose_new_neighbors_loop(self):
        # Call function
        self.update_k_pref_neighbors()
        # Reset timer
        t = threading.Timer(self.p, self.choose_new_neighbors_loop)
        t.daemon = True
        t.start()

    def choke(self, peer):
        # Verify peer connection exists
        with self.connections_lock:
            conn = self.connections_map.get(peer.peer_id)

        # If connection does not exist, return
        if conn is None:
            return

        # Choke peer and log
        conn.peer_choked = True
        send_msg(conn.sock, MsgType.CHOKE, b'')

    def unchoke(self, peer):
        # Verify peer connection exists
        with self.connections_lock:
            conn = self.connections_map.get(peer.peer_id)

        # If connection does not exist, return
        if conn is None:
            return

        # Unchoke peer and log
        conn.peer_choked = False
        send_msg(conn.sock, MsgType.UNCHOKE, b'')

    def update_k_pref_neighbors(self):

        # Get list of peers
        with self.connections_lock:
            peer_list = dict(self.connections_map)

        # Find interested neighbors
        interested_peers = [peer_id for peer_id, conn in peer_list.items() if conn.peer_interested]

        # Get download rates from each interested peer
        with self.download_counter_lock:
            download_rates = {peer_id: self.download_counter.get(peer_id, 0) for peer_id in interested_peers}
            # Reset counts for next interval
            self.download_counter = {}

        # Sort by download rate, use a random tiebreak
        if self.bitfield.all(1):
            new_k_neighbors = random.sample(interested_peers, min(self.k, len(interested_peers)))
        else:
            new_bors = sorted(interested_peers, key=lambda p: (download_rates[p], random.random()), reverse=True)
            new_k_neighbors = new_bors[:self.k]

        # Log preferred neighbors
        self.logMsg(f"Peer [{self.peerID}] has the preferred neighbors [{','.join(map(str, sorted(new_k_neighbors)))}].")

        # Update choke/unchoke
        for peer_id, conn in peer_list.items():
            # Send unchoke msg to new k neighbors if choked
            if peer_id in new_k_neighbors and conn.peer_choked:
                conn.peer_choked = False
                send_msg(conn.sock, MsgType.UNCHOKE, b'')
            # Choke unchoked neighbors that are not k favorited
            elif peer_id not in new_k_neighbors and not conn.peer_choked:
                with self.optimistic_lock:
                    is_optimistic = (peer_id == self.optimistic_neighbor)
                if not is_optimistic:
                    conn.peer_choked = True
                    send_msg(conn.sock, MsgType.CHOKE, b'')

    def optimistic_unchoke(self):
        # Get list of peers
        with self.connections_lock:
            peer_list = dict(self.connections_map)

        # Find interested and choked neighbors
        choked_peers = [peer_id for peer_id, conn in peer_list.items() if conn.peer_interested and conn.peer_choked]

        # Randomly select a peer, if it exists
        if not choked_peers:
            return
        random_peer_id = random.choice(choked_peers)
        conn = peer_list[random_peer_id]

        with self.optimistic_lock:
            self.optimistic_neighbor = random_peer_id

        # Unchoke peer
        conn.peer_choked = False
        send_msg(conn.sock, MsgType.UNCHOKE, b'')

        # Send unchoke message
        self.logMsg(f"Peer [{self.peerID}] has the optimistically unchoked neighbor [{random_peer_id}].")

    def logMsg(self, message):
        lock = get_log_lock(self.peerID)
        with lock:
            with open(f"log_peer_{self.peerID}.log", "a") as x:
                x.write(f"[{datetime.now()}]: {message}\n")
