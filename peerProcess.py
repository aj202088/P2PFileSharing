import sys
import os
import socket
import threading
from math import ceil
from protocol import *
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
    # Grabs peerID from cmd line
    peerID = int(sys.argv[1])
    commInf, pieces = readComm()
    allPeerInf = readPeer()
    peerInf = findPeerInf(allPeerInf, peerID)
    # Makes bitfield dependent if they have file or not
    bitfield = [1] * pieces if peerInf[3] == 1 else [0] * pieces
    createPeerDir(peerID)
    # Create peer object
    peer_obj = Peer(commInf, peerInf, allPeerInf, pieces)
    # Creates a thread for starting up the peer
    serv = threading.Thread(target=servStart, args=(peerInf, bitfield), daemon=True)
    serv.start()
    prevPeers(allPeerInf, peerInf, bitfield)
    # As long as server is up, main wont end
    serv.join()


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
def servStart(currPeerInf, bitfield):
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
        # Creates a new thread to work on background connection looping; lets this peer keep listening for future connections
        threading.Thread(target=conn, args=(connection, currPeerInf[0], bitfield), daemon=True).start()


# Loops through previous peers, establishing connections
def prevPeers(allPeerInf, currPeerInf, bitfield):
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
                # Handle connection looping on a background thread; lets this peer keep establishing socket connections to other previous peers
                threading.Thread(target=conn, args=(connectingPeer, currPeerInf[0], bitfield, remoteID),
                                 daemon=True).start()
            except ConnectionRefusedError:
                print(f"Failed connecting Peer {currPeerInf[0]} to Peer {otherPeers[0]}")
        if otherPeers[0] == currPeerInf[0]:
            break


# Connection funct
def conn(connection, peerID, bitfield, remoteID=None):
    try:
        # No previous handshake; do it here
        if (remoteID is None):
            remoteID = recv_handshake(connection)
            send_handshake(connection, int(peerID))
        # Send 'bitfield' message to know file pieces
        if sum(bitfield) > 0:
            send_msg(connection, MsgType.BITFIELD, bytes(bitfield))
        # Get messages from peer
        while True:
            msgType, data = recv_message(connection)
            print(f"Got: {msgType.name} From: {remoteID}")
    except ConnectionError:
        print(f"Lost peer connection {remoteID}")


if __name__ == "__main__":
    main()
