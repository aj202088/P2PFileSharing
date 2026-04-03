import sys
import os
import socket
import threading
from math import ceil
from protocol import send_handshake, recv_handshake, send_msg, recv_message, unpack_piece_index
from constants import MsgType
from bitfield_logic import (
    create_bitfield_state,
    pack_bitfield,
    handle_bitfield as process_bitfield,
    handle_have as process_have,
    get_my_bitfield
)
from peer import Peer

'''
CITATIONS:
https://www.w3schools.com/python/python_file_open.asp - reading files in python
https://www.geeksforgeeks.org/python/create-a-directory-in-python/ - creating directory in python
https://www.geeksforgeeks.org/python/socket-programming-python/ - socket programming basics in python
https://realpython.com/python-sockets/ - socket programming basics in python
'''

# Main
def main():
    try:
        # Grabs peerID from cmd line
        peerID = int(sys.argv[1])
        commInf, pieces = readComm()
        allPeerInf = readPeer()
        peerInf = findPeerInf(allPeerInf, peerID)
        if peerInf is None:
            print(f"Peer {peerID} not found in PeerInfo.cfg")
            sys.exit(1)

        # Makes bitfield dependent if they have file or not
        bitfield = [1] * pieces if peerInf[3] == 1 else [0] * pieces
        bitfield_state = create_bitfield_state(bitfield)
        createPeerDir(peerID)

        peer_obj = Peer(
            [commInf["NumberOfPreferredNeighbors"], commInf["UnchokingInterval"],
             commInf["OptimisticUnchokingInterval"], commInf["FileName"],
             commInf["FileSize"], commInf["PieceSize"]],
            peerInf, allPeerInf, pieces
        )

        serv = threading.Thread(target=servStart, args=(peerInf, bitfield_state, pieces), daemon=True)
        serv.start()
        prevPeers(allPeerInf, peerInf, bitfield_state, pieces)
        serv.join()

    except KeyboardInterrupt:
        print(f"\nPeer {peerID} shutting down")


# Creates Directory as peer_peerID
def createPeerDir(peerID):
    peerDir = f"peer_{peerID}"
    if not os.path.exists(peerDir):
        os.mkdir(peerDir)


# Reads Common.cfg; returning a dict of the file info & # of pieces calculated
def readComm():
    filePath = 'Common.cfg'
    commInf = {}
    with open(filePath) as file:
        for fileLine in file:
            key, val = fileLine.split()
            try:
                commInf[key] = int(val)
            except ValueError:
                commInf[key] = val
    pieces = ceil(commInf["FileSize"] / commInf["PieceSize"])
    return commInf, pieces


# Reads PeerInfo.cfg; return list of all peer info, each peer info a list themselves in the form of [peerID, host, port#, hasFile]
def readPeer():
    filePath = 'PeerInfo.cfg'
    allPeerInf = []
    with open(filePath) as file:
        for fileLine in file:
            vals = fileLine.split()
            # [peerID, host, port#, hasFile]
            allPeerInf.append([int(vals[0]), vals[1], int(vals[2]), int(vals[3])])
    return allPeerInf


# Grabs the specific peer's info from allPeerInf; return list [peerID, host, port#, hasFile]
def findPeerInf(allPeerInf, peerID):
    for peer in allPeerInf:
        if peer[0] == peerID:
            host = peer[1]
            port = peer[2]
            hasFile = peer[3]
            return [peerID, host, port, hasFile]


# Puts the peer socket up into listening, accepting other peers who connect
def servStart(currPeerInf, bitfield_state, pieces):
    try:
        # Peer server socket creation + set to listening
        serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except socket.error as err:
        print(f"Peer {currPeerInf[0]} failed socket creation. Err: {err}")
    serverSocket.bind((currPeerInf[1], currPeerInf[2]))
    serverSocket.listen()
    print(f"Peer {currPeerInf[0]} listening to {currPeerInf[2]}")
    while True:
        # Accepting socket connection
        connection, address = serverSocket.accept()
        print(f"Peer {currPeerInf[0]} has connection from: {address}")
        # Creates a new PeerConnection thread for each incoming connection
        PeerConnection(connection, currPeerInf[0], bitfield_state, pieces).start()


# Loops through previous peers, establishing connections
def prevPeers(allPeerInf, currPeerInf, bitfield_state, pieces):
    for otherPeers in allPeerInf:
        if otherPeers[0] != currPeerInf[0]:
            try:
                # Creates a socket to connect to previous peer
                connectingPeer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                connectingPeer.connect((otherPeers[1], otherPeers[2]))
                # Handshake between previous peer + this active peer
                send_handshake(connectingPeer, currPeerInf[0])
                # Handshake received
                remoteID = recv_handshake(connectingPeer)
                # Handle connection on a PeerConnection thread
                PeerConnection(connectingPeer, currPeerInf[0], bitfield_state, pieces, remoteID).start()
            except ConnectionRefusedError:
                print(f"Failed connecting Peer {currPeerInf[0]} to Peer {otherPeers[0]}")
        if otherPeers[0] == currPeerInf[0]:
            break


# Sophia's connection below
# Handles a single peer connection in a background thread
class PeerConnection(threading.Thread):

    def __init__(self, sock, local_id, bitfield_state, pieces, remote_id=None):
        super().__init__(daemon=True)
        self.sock = sock                        # tcp socket for this connection
        self.local_id = local_id                # this peer's own ID
        self.remote_id = remote_id              # the other peer's ID (None if incoming)
        self.bitfield_state = bitfield_state    # state for managing bitfields
        self.num_pieces = pieces                # Total number of pieces
        self.remote_bitfield = None             # will be set when we get BITFIELD msg
        self.am_choked = True                   # are we choked by the remote peer
        self.am_interested = False              # are we interested in the remote peer
        self.peer_choked = True                 # is the remote peer choked by us
        self.peer_interested = False            # is the remote peer interested in us

    # Performs handshake; incoming peers receive first, outgoing already done
    def do_handshake(self):
        if self.remote_id is None:
            # Incoming: receive first, we don't know who they are, then send our handshake back
            self.remote_id = recv_handshake(self.sock)
            send_handshake(self.sock, self.local_id)
            print(f"[Peer {self.local_id}] Accepted handshake from Peer {self.remote_id}")
        else:
            # Outgoing: handshake already exchanged
            print(f"[Peer {self.local_id}] Completed handshake with Peer {self.remote_id}")

    # Sends bitfield to remote peer if we have any pieces
    def send_bitfield(self):
        local_bitfield = get_my_bitfield(self.bitfield_state)
        if sum(local_bitfield) > 0:
            send_msg(self.sock, MsgType.BITFIELD, pack_bitfield(local_bitfield))
            print(f"[Peer {self.local_id}] Sent BITFIELD to Peer {self.remote_id}")

    # Remote peer is choking us; we can no longer request pieces
    def handle_choke(self, payload):
        self.am_choked = True
        print(f"[Peer {self.local_id}] Choked by Peer {self.remote_id}")

    # Remote peer unchoked us; we can now request pieces
    def handle_unchoke(self, payload):
        self.am_choked = False
        print(f"[Peer {self.local_id}] Unchoked by Peer {self.remote_id}")

    # Remote peer is interested in our pieces
    def handle_interested(self, payload):
        self.peer_interested = True
        print(f"[Peer {self.local_id}] Peer {self.remote_id} is INTERESTED")

    # Remote peer is not interested in our pieces
    def handle_not_interested(self, payload):
        self.peer_interested = False
        print(f"[Peer {self.local_id}] Peer {self.remote_id} is NOT INTERESTED")

    # Remote peer has a new piece; update their bitfield
    def handle_have(self, payload):
        piece_index, interest_msg = process_have(self.bitfield_state, self.remote_id, payload)
        print(f"[Peer {self.local_id}] Peer {self.remote_id} has piece {piece_index}")

        if interest_msg == MsgType.INTERESTED:
            self.am_interested = True
            send_msg(self.sock, MsgType.INTERESTED, b'')
            print(f"[Peer {self.local_id}] Sent INTERESTED to Peer {self.remote_id}")
        elif interest_msg == MsgType.NOT_INTERESTED:
            self.am_interested = False
            send_msg(self.sock, MsgType.NOT_INTERESTED, b'')
            print(f"[Peer {self.local_id}] Sent NOT_INTERESTED to Peer {self.remote_id}")

    # Stores remote bitfield and sends INTERESTED or NOT_INTERESTED
    def handle_bitfield(self, payload):
        interest_msg = process_bitfield(self.bitfield_state, self.remote_id, payload, self.num_pieces)
        print(f"[Peer {self.local_id}] Received BITFIELD from Peer {self.remote_id}")

        if interest_msg == MsgType.INTERESTED:
            self.am_interested = True
            send_msg(self.sock, MsgType.INTERESTED, b'')
            print(f"[Peer {self.local_id}] Sent INTERESTED to Peer {self.remote_id}")
        else:
            self.am_interested = False
            send_msg(self.sock, MsgType.NOT_INTERESTED, b'')
            print(f"[Peer {self.local_id}] Sent NOT_INTERESTED to Peer {self.remote_id}")

    # Remote peer is requesting a piece
    def handle_request(self, payload):
        piece_index = unpack_piece_index(payload)
        print(f"[Peer {self.local_id}] Peer {self.remote_id} requested piece {piece_index}")

    # We received a piece from remote peer
    def handle_piece(self, payload):
        piece_index = unpack_piece_index(payload[:4])
        print(f"[Peer {self.local_id}] Received piece {piece_index} from Peer {self.remote_id}")

    # Routes incoming messages to the correct handler
    def dispatch(self, msg_type, payload):
        handlers = {
            MsgType.CHOKE:          self.handle_choke,
            MsgType.UNCHOKE:        self.handle_unchoke,
            MsgType.INTERESTED:     self.handle_interested,
            MsgType.NOT_INTERESTED: self.handle_not_interested,
            MsgType.HAVE:           self.handle_have,
            MsgType.BITFIELD:       self.handle_bitfield,
            MsgType.REQUEST:        self.handle_request,
            MsgType.PIECE:          self.handle_piece,
        }
        handler = handlers.get(msg_type)
        if handler:
            handler(payload)
        else:
            print(f"[Peer {self.local_id}] Unknown message type: {msg_type}")

    # Thread entry point; runs handshake, bitfield, then message loop
    def run(self):
        try:
            self.do_handshake()
            self.send_bitfield()
            while True:
                msg_type, payload = recv_message(self.sock)
                print(f"[Peer {self.local_id}] Got {msg_type.name} from Peer {self.remote_id}")
                self.dispatch(msg_type, payload)
        except ConnectionError:
            print(f"[Peer {self.local_id}] Lost connection to Peer {self.remote_id}")
        finally:
            self.sock.close()


if __name__ == "__main__":
    main()