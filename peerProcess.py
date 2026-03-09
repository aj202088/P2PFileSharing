import sys
import os
import socket
import threading
from math import ceil
from protocol import *

'''
CITATIONS:
https://www.w3schools.com/python/python_file_open.asp - reading files in python
https://www.geeksforgeeks.org/python/create-a-directory-in-python/ - creating directory in python
https://www.geeksforgeeks.org/python/socket-programming-python/ - socket programming basics in python
https://realpython.com/python-sockets/ - socket programming basics in python
'''
# Main
def main():
    peerID = int(sys.argv[1]) # Grabs peerID from cmd line
    commInf, pieces = readComm()
    allPeerInf = readPeer()
    peerInf = findPeerInf(allPeerInf, peerID)
    bitfield = [1] * pieces if peerInf[3] == 1 else [0] * pieces # Makes bitfield dependent if they have file or not
    createPeerDir(peerID)
    serv = threading.Thread(target=servStart, args=(peerInf, bitfield), daemon=True) # Creates a thread for starting up the peer
    serv.start()
    prevPeers(allPeerInf, peerInf, bitfield)
    serv.join() # As long as server is up, main wont end

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
            allPeerInf.append([int(vals[0]), vals[1], int(vals[2]), int(vals[3])]) # [peerID, host, port#, hasFile]
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
    # Peer server socket creation + set to listening
    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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
                send_handshake(connectingPeer, currPeerInf[0]) # Handshake between previous peer + this active peer
                remoteID = recv_handshake(connectingPeer) # Handshake received
                # Handle connection looping on a background thread; lets this peer keep establishing socket connections to other previous peers
                threading.Thread(target=conn, args=(connectingPeer, currPeerInf[0], bitfield, remoteID), daemon=True).start()
            except ConnectionRefusedError:
                print(f"Failed connecting Peer {currPeerInf[0]} to Peer {otherPeers[0]}")
        if otherPeers[0] == currPeerInf[0]:
            break

# Connection funct.
def conn(connection, peerID, bitfield, remoteID=None):
    try:
        if (remoteID is None):
            remoteID = recv_handshake(connection)
            send_handshake(connection, int(peerID))
        if sum(bitfield) > 0:
            send_msg(connection, MsgType.BITFIELD, bytes(bitfield))
        while True:
            msgType, data = recv_message(connection)
            print(f"Got: {msgType.name} From: {remoteID}")
    except ConnectionError:
        print(f"lost peer connection {remoteID}")

if __name__ == "__main__":
    main()
