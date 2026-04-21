import sys
import os
import socket
import threading
from datetime import datetime
from math import ceil
from protocol import send_handshake, recv_handshake, send_msg, recv_message, unpack_piece_index, pack_piece_index
from constants import MsgType
from bitfield_logic import (
    create_bitfield_state,
    pack_bitfield,
    handle_bitfield as process_bitfield,
    handle_have as process_have,
    get_my_bitfield,
    set_my_piece,
    reevaluate_all_interest,
    pick_piece_to_request,
    mark_piece_requested,
    unmark_piece_requested,
    count_my_pieces,
    has_complete_file,
    unpack_bitfield,
)
from peer import Peer

'''
CITATIONS:
https://www.w3schools.com/python/python_file_open.asp - reading files in python
https://www.geeksforgeeks.org/python/reading-binary-files-in-python/ - reading chunks of files in python
https://www.geeksforgeeks.org/python/create-a-directory-in-python/ - creating directory in python
https://www.geeksforgeeks.org/python/socket-programming-python/ - socket programming basics in python
https://realpython.com/python-sockets/ - socket programming basics in python
https://realpython.com/python-thread-lock/ - threading lock usage for shared state
https://www.w3schools.com/python/python_datetime.asp - date + time for logging
https://www.geeksforgeeks.org/python/python-os-path-join-method/ - file pathing
https://stackoverflow.com/questions/1489669/how-to-exit-the-entire-application-from-a-python-thread - Exiting threaded process
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
        dir = createPeerDir(peerID)

        peer_obj = Peer(
            [commInf["NumberOfPreferredNeighbors"], commInf["UnchokingInterval"],
             commInf["OptimisticUnchokingInterval"], commInf["FileName"],
             commInf["FileSize"], commInf["PieceSize"]],
            peerInf, allPeerInf, pieces
        )

        # Shared dict for mapping remote_id to peerconnection; protected by connections_lock
        connections_map = {}
        connections_lock = threading.Lock()

        # common config needed for piece handlers with file name, piece size, and peer directory
        common_cfg = {
            "file_name": commInf["FileName"],
            "file_size": commInf["FileSize"],
            "piece_size": commInf["PieceSize"],
            "peer_dir": f"peer_{peerID}",
            "num_pieces": pieces,
        }
        if peerInf[3] == 1:
            split(common_cfg, dir)
        serv = threading.Thread(
            target=servStart,
            args=(peerInf, bitfield_state, pieces, connections_map, connections_lock, common_cfg),
            daemon=True)
        serv.start()
        prevPeers(allPeerInf, peerInf, bitfield_state, pieces, connections_map, connections_lock, common_cfg)
        serv.join()

    except KeyboardInterrupt:
        print(f"\nPeer {peerID} shutting down")

# Splits file by pieceSize, then saves the pieces as its own file into peerDir
def split(commInfo, peerDir):
    filePath = os.path.join(peerDir, commInfo["file_name"])
    pieceSize = commInfo["piece_size"]
    with open(filePath, 'rb') as x:
        cnt = 0
        while True:
            piece = x.read(pieceSize)
            if not piece:
                break
            save_piece(peerDir, cnt, piece)
            cnt += 1

# Creates Directory as peer_peerID
def createPeerDir(peerID):
    peerDir = f"peer_{peerID}"
    if not os.path.exists(peerDir):
        os.mkdir(peerDir)
    return peerDir


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
def servStart(currPeerInf, bitfield_state, pieces, connections_map, connections_lock, common_cfg):
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
        conn = PeerConnection(
            connection, currPeerInf[0], bitfield_state, pieces,
            connections_map, connections_lock, common_cfg
        )
        conn.start()


# Loops through previous peers, establishing connections
def prevPeers(allPeerInf, currPeerInf, bitfield_state, pieces, connections_map, connections_lock, common_cfg):
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
                conn = PeerConnection(
                    connectingPeer, currPeerInf[0], bitfield_state, pieces,
                    connections_map, connections_lock, common_cfg, remote_id=remoteID
                )
                conn.start()
            except ConnectionRefusedError:
                print(f"Failed connecting Peer {currPeerInf[0]} to Peer {otherPeers[0]}")
        if otherPeers[0] == currPeerInf[0]:
            break


# Handles a single peer connection in a background thread
class PeerConnection(threading.Thread):

    def __init__(self, sock, local_id, bitfield_state, pieces,
                 connections_map, connections_lock, common_cfg, remote_id=None):
        super().__init__(daemon=True)
        self.sock = sock                        # tcp socket for this connection
        self.local_id = local_id                # this peer's own ID
        self.remote_id = remote_id              # the other peer's ID (None if incoming)
        self.bitfield_state = bitfield_state    # state for managing bitfields
        self.num_pieces = pieces                # Total number of pieces
        self.connections_map = connections_map  # shared dict: map of active connections
        self.connections_lock = connections_lock# lock for accessing connections_map
        self.common_cfg = common_cfg            # common configuration
        self.remote_bitfield = None             # will be set when we get BITFIELD msg
        self.am_choked = True                   # are we choked by the remote peer
        self.am_interested = False              # are we interested in the remote peer
        self.peer_choked = True                 # is the remote peer choked by us
        self.peer_interested = False            # is the remote peer interested in us
        self.in_flight_piece = None             # pieces we've requested but haven't received yet

    # Performs handshake; incoming peers receive first, outgoing already done
    def do_handshake(self):
        if self.remote_id is None:
            # Incoming: receive first, we don't know who they are, then send our handshake back
            self.remote_id = recv_handshake(self.sock)
            send_handshake(self.sock, self.local_id)
            print(f"[Peer {self.local_id}] Accepted handshake from Peer {self.remote_id}")
            self.logMsg(f"Peer [{self.local_id}] is connected from Peer [{self.remote_id}].")
        else:
            # Outgoing: handshake already exchanged
            print(f"[Peer {self.local_id}] Completed handshake with Peer {self.remote_id}")
            self.logMsg(f"Peer [{self.local_id}] makes a connection to Peer [{self.remote_id}].")

    # Register this connection in the shared map so HAVE broadcasts can reach it
    def register_connection(self):
        with self.connections_lock:
            self.connections_map[self.remote_id] = self
 
    # Remove this connection from the shared map on disconnect
    def unregister_connection(self):
        with self.connections_lock:
            self.connections_map.pop(self.remote_id, None)

    # Sends bitfield to remote peer if we have any pieces
    def send_bitfield(self):
        local_bitfield = get_my_bitfield(self.bitfield_state)
        if sum(local_bitfield) > 0:
            send_msg(self.sock, MsgType.BITFIELD, pack_bitfield(local_bitfield))
            print(f"[Peer {self.local_id}] Sent BITFIELD to Peer {self.remote_id}")

    # Remote peer is choking us; cancel any in-flight request and stop requesting
    def handle_choke(self, payload):
        self.am_choked = True
        # Unmark any pieces we had requested but haven't received yet, since we're now choked
        if self.in_flight_piece is not None:
            unmark_piece_requested(self.bitfield_state, self.in_flight_piece)
            self.in_flight_piece = None
        print(f"[Peer {self.local_id}] Choked by Peer {self.remote_id}")
        self.logMsg(f"Peer [{self.local_id}] is choked by [{self.remote_id}].")

    # Remote peer unchoked us; we can now request pieces
    def handle_unchoke(self, payload):
        self.am_choked = False
        print(f"[Peer {self.local_id}] Unchoked by Peer {self.remote_id}")
        self.logMsg(f"Peer [{self.local_id}] is unchoked by [{self.remote_id}].")
        # Try to request piece since now we're unchoked
        self.maybe_request_piece()

    # Remote peer is interested in our pieces
    def handle_interested(self, payload):
        self.peer_interested = True
        self.logMsg(f"Peer [{self.local_id}] received the 'interested' message from [{self.remote_id}].")
        print(f"[Peer {self.local_id}] Peer {self.remote_id} is INTERESTED")

    # Remote peer is not interested in our pieces
    def handle_not_interested(self, payload):
        self.peer_interested = False
        self.logMsg(f"Peer [{self.local_id}] received the 'not interested' message from [{self.remote_id}].")
        print(f"[Peer {self.local_id}] Peer {self.remote_id} is NOT INTERESTED")

    # Remote peer has a new piece; update their bitfield and reevaluate interest
    def handle_have(self, payload):
        piece_index, interest_msg = process_have(self.bitfield_state, self.remote_id, payload)
        if self.remote_bitfield is not None:
            self.remote_bitfield[piece_index] = 1
        self.logMsg(f"Peer [{self.local_id}] received the 'have' message from [{self.remote_id}] for the piece [{piece_index}].")
        print(f"[Peer {self.local_id}] Peer {self.remote_id} has piece {piece_index}")
        if interest_msg == MsgType.INTERESTED:
            self.am_interested = True
            send_msg(self.sock, MsgType.INTERESTED, b'')
            print(f"[Peer {self.local_id}] Sent INTERESTED to Peer {self.remote_id}")
        elif interest_msg == MsgType.NOT_INTERESTED:
            self.am_interested = False
            send_msg(self.sock, MsgType.NOT_INTERESTED, b'')
            print(f"[Peer {self.local_id}] Sent NOT_INTERESTED to Peer {self.remote_id}")
        self.globalCheck()

    # Stores remote bitfield and sends INTERESTED or NOT_INTERESTED
    def handle_bitfield(self, payload):
        self.remote_bitfield = unpack_bitfield(payload, self.num_pieces)
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
        self.globalCheck()

    # Remote peer is requesting a piece
    def handle_request(self, payload):
        piece_index = unpack_piece_index(payload)
        print(f"[Peer {self.local_id}] Peer {self.remote_id} requested piece {piece_index}")
        if self.peer_choked:
            return
        if not os.path.exists(os.path.join(self.common_cfg["peer_dir"], f"{piece_index}")):
            return
        with open(os.path.join(self.common_cfg["peer_dir"], f"{piece_index}"), 'rb') as i:
            msgPayload = pack_piece_index(piece_index) + i.read()
            send_msg(self.sock, MsgType.PIECE, msgPayload)
        print(f"[Peer {self.local_id}] Sent piece {piece_index} to Peer {self.remote_id}")
        
    # Assembles the file by writing every piece file into file_name in peer_dir
    def assembleFile(self):
        with open(os.path.join(self.common_cfg["peer_dir"], self.common_cfg["file_name"]), 'wb') as out:
            for i in range(self.common_cfg["num_pieces"]):
                with open(os.path.join(self.common_cfg["peer_dir"], f"{i}"), 'rb') as x:
                    out.write(x.read())

    # Handles check for global completion
    def globalCheck(self):
        if not has_complete_file(self.bitfield_state):
            return
        with self.connections_lock:
            total = list(self.connections_map.values())
        completed = 0
        for i in total:
            bitField = i.remote_bitfield
            if bitField and all(bitField):
                completed += 1
        if completed == len(total):
            print(f"[Peer {self.local_id}] All done")
            os._exit(0)

    # Handles receiving a piece: saves to disk, updates bitfield, broadcasts HAVE,
    # re-evaluates interest toward all neighbors, then requests the next piece
    def handle_piece(self, payload):

        # 1. Parse piece index and raw data
        piece_index = unpack_piece_index(payload[:4])
        piece_data = payload[4:]
        print(f"[Peer {self.local_id}] Received piece {piece_index} from Peer {self.remote_id}")

        # 2. Save piece to disk
        save_piece(self.common_cfg["peer_dir"], piece_index, piece_data)
        self.logMsg(f"Peer [{self.local_id}] has downloaded the piece [{piece_index}] from [{self.remote_id}]. Now the number of pieces it has is [{count_my_pieces(self.bitfield_state)}].")

        # 3. Update our bitfield to mark we now have this piece
        set_my_piece(self.bitfield_state, piece_index)
        num_pieces_now = count_my_pieces(self.bitfield_state)
        print(f"[Peer {self.local_id}] Now has {num_pieces_now}/{self.num_pieces} pieces")

        # 4. Check for local completion of the file
        if has_complete_file(self.bitfield_state):
            self.logMsg(f"Peer [{self.local_id}] has downloaded the complete file.")
            print(f"[Peer {self.local_id}] Now has file downloaded")
            self.assembleFile()
            print(f"[Peer {self.local_id}] Now has file assembled")

        # 5. Unmark in-flight tracking since we got the piece
        unmark_piece_requested(self.bitfield_state, piece_index)
        self.in_flight_piece = None

        # 6. Broadcast HAVE to all other connections
        self.broadcast_have(piece_index)

        # 7. Re-evaluate interest toward all neighbors 
        self.reevaluate_and_send_interest()

        # 8. Request the next piece from this peer if still unchoked
        if not self.am_choked:
            self.maybe_request_piece()

        # 9. Check if globally done
        self.globalCheck()
        
        
    # Picks a random missing piece that the remote has and sends a REQUEST if not choked
    # CITATION: spec 'request and piece' section - random selection, no pipelining
    def maybe_request_piece(self):
        if self.am_choked:
            return
 
        piece_index = pick_piece_to_request(self.bitfield_state, self.remote_id)
        if piece_index is None:
            # Nothing left to request from this peer right now
            return
 
        # Mark as in-flight before sending so another connection can't grab it
        mark_piece_requested(self.bitfield_state, piece_index)
        self.in_flight_piece = piece_index
 
        send_msg(self.sock, MsgType.REQUEST, pack_piece_index(piece_index))
        print(f"[Peer {self.local_id}] Sent REQUEST for piece {piece_index} to Peer {self.remote_id}")

    # Broadcasts HAVE to all connected peers after receiving a new piece so they can update their bitfields
    # CITATION: spec 'interested and not interested' section - peers send interested/not interested after receiving HAVE
    def broadcast_have(self, piece_index):
        have_payload = pack_piece_index(piece_index)
        with self.connections_lock:
            peers_to_notify = list(self.connections_map.items())
 
        for remote_id, conn in peers_to_notify:
            if remote_id == self.remote_id:
                continue  # skip the peer we just got the piece from
            try:
                send_msg(conn.sock, MsgType.HAVE, have_payload)
                print(f"[Peer {self.local_id}] Broadcast HAVE piece {piece_index} to Peer {remote_id}")
            except Exception as e:
                print(f"[Peer {self.local_id}] Failed to send HAVE to Peer {remote_id}: {e}")

    # Re-checks interest toward all neighbors after gaining a piece and sends updated messages
    def reevaluate_and_send_interest(self):
        updates = reevaluate_all_interest(self.bitfield_state)
        updatedPref = set()
        with self.connections_lock:
            conn_snapshot = dict(self.connections_map)
 
        for peer_id, msg_type in updates:
            conn = conn_snapshot.get(peer_id)
            if conn is None:
                continue
            try:
                if msg_type == MsgType.INTERESTED:
                    send_msg(conn.sock, MsgType.INTERESTED, b'')
                    print(f"[Peer {self.local_id}] Sent INTERESTED to Peer {peer_id} (re-eval)")
                    updatedPref.add(peer_id)
                elif msg_type == MsgType.NOT_INTERESTED:
                    send_msg(conn.sock, MsgType.NOT_INTERESTED, b'')
                    print(f"[Peer {self.local_id}] Sent NOT_INTERESTED to Peer {peer_id} (re-eval)")
            except Exception as e:
                print(f"[Peer {self.local_id}] Failed to send interest update to Peer {peer_id}: {e}")
        with self.bitfield_state["lock"]:
            prevPref = self.bitfield_state["prev_pref_neighbors"]
            if updatedPref != prevPref:
                self.bitfield_state["prev_pref_neighbors"] = set(updatedPref)
                self.logMsg(f"Peer [{self.local_id}] has the preferred neighbors [{','.join(map(str, sorted(updatedPref)))}]")

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
            self.register_connection()
            self.send_bitfield()
            while True:
                msg_type, payload = recv_message(self.sock)
                print(f"[Peer {self.local_id}] Got {msg_type.name} from Peer {self.remote_id}")
                self.dispatch(msg_type, payload)
        except ConnectionError:
            print(f"[Peer {self.local_id}] Lost connection to Peer {self.remote_id}")
        finally:
            # release any in-flight piece if we were waiting for one from this peer
            if self.in_flight_piece is not None:
                unmark_piece_requested(self.bitfield_state, self.in_flight_piece)
            self.unregister_connection()
            self.sock.close()

    # Logging function
    def logMsg(self, message):
        with open(f"log_peer_{self.local_id}.log", "a") as x:
            x.write(f"[{datetime.now()}]: {message}\n")
    
# Helper function to save a piece's data to disk in the correct peer directory
def save_piece(peer_dir, piece_index, data):
    piece_path = os.path.join(peer_dir, f"{piece_index}")
    with open(piece_path, 'wb') as f:
        f.write(data)

if __name__ == "__main__":
    main()