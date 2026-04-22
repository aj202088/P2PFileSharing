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
- Implemented the `PeerConnection` thread class to handle incoming and outgoing peer connections.
- Implemented handshake flow for both incoming and outgoing connections.
- Implemented message dispatch loop routing incoming messages to appropriate handlers.
- Implemented message handlers for `CHOKE`, `UNCHOKE`, `INTERESTED`, `NOT_INTERESTED`, `HAVE`, `BITFIELD`, `REQUEST`, and `PIECE` messages.

#### Part 2:
- Implemented random piece selection from pieces remote peer has that we don't and haven't already requested.
- Implemented in-flight tracking shared across all connections so the same piece doesn't get requested twice.
- Implemented `REQUEST` sending that triggers when unchoked and again after each piece is received.
- Implemented `PIECE` handling to save the piece to disk, update our bitfield, and kick off the next request.
- Implemented `HAVE` broadcast to all connected peers whenever we finish downloading a new piece.
- Implemented interest re-evaluation toward all neighbors after gaining a piece since we may no longer need some of them.
- Implemented a shared connections map so peer threads can reach each other for broadcasting.

### Haylee Zuba
#### Part 1:
#### Part 2:


### Julian Garcia
#### Part 1:
#### Part 2:
