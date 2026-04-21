# P2PFileSharing
CNT4007 Computer Networks Project
Project Group #2 Members:
    Sophia Cardona Nader
    Julian Garcia
    Ashton Penalacia
    Haylee Zuba

How to run:
    python peerProcess.py peerID

Ex:
    python peerProcess.py 1001

How we tested on our end so far:
    Primarily through localhost, each peer on different ports
    It doesn't terminate itself on its own yet. Must be exited manually.

Bitstring might need to be installed individually, using pip install bitstring


## Team Member Contributions

### Ashton Penalacia

#### Part 1: Protocol Implementation
 - Implemented handshake packing and unpacking.
 - Implemented peer message packing and unpacking, including length, type, and payload handling.
 - Implemented `read_exact(n)` to ensure complete protocol reads across TCP sockets.


#### Part 2: Bitfield, Peer State, and Interest Logic
 - Implemented bitfield packing and unpacking logic for message payloads.
 - Implemented shared state structure for storing local and neighbor peer bitfield.
 - Implemented `BITFIELD` message handling.
 - Implemented `HAVE` message handling.
 - Implemented peer interest evaluation logic based on missing piece comparison.
 - Implemented sending `INTERESTED` and `NOT_INTERESTED` decisions.
 - Integrated bitfield and interest logic into the peer runtime with minimal changes to the existing connection flow.


### Sophia Cardona Náder
#### Part 1:
#### Part 2:


### Haylee Zuba
#### Part 1:
#### Part 2:


### Julian Garcia
#### Part 1:
#### Part 2:
