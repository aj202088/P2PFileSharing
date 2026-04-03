import threading
from protocol import send_msg, pack_piece_index, unpack_piece_index
from constants import MsgType


# Logic for handling bitfield messages and maintaining the state of which pieces have been downloaded
def create_bitfield_state(my_bitfield):
    return {
        "my_bitfiled": my_bitfield,
        "neighbor_bitfields": {},
        "interest_state": {},
        "connections": {},
        "lock": threading.Lock()
    }


# Function to register a new connection for a peer and initialize state for that peer
def register_connection(state, peer_id, connection):
    # Initialize state for new peer
    with state["lock"]:
        # Only add connection if it doesn't already exist to avoid overwriting existing state
        if peer_id not in state["connections"]:
            state["connections"][peer_id] = connection


# Function to remove a connection and all associated state for a peer
def remove_connection(state, peer_id):
    with state["lock"]:
        # Remove connection for the peer if exists
        if peer_id in state["connections"]:
            del state["connections"][peer_id]
        
        # Remove neighbor bitfield for the peer if exists
        if peer_id in state["neighbor_bitfields"]:
            del state["neighbor_bitfields"][peer_id]
        
        # Remove interest state for the peer if exists
        if peer_id in state["interest_state"]:
            del state["interest_state"][peer_id]


# Functions to pack bitfields into bytes for sending over the network
def pack_bitfield(bitfield):
    packed = bytearray()
    curr_byte = 0

    # Iterate through bitfield and pack bits into bytes
    for i, bit in enumerate(bitfield):
        # If the bit is set, shift it to the correct position and add it to the current byte
        if bit:
            shift = 7 - (i % 8)
            curr_byte |= (1 << shift)
        
        # If 8 bits processed, append current byte to the packed result and reset the current byte
        if (i % 8) == 7:
            packed.append(curr_byte)
            curr_byte = 0
    
    # If there are remaining bits not in byte, append the last byte to the packed result
    if (len(bitfield) % 8) != 0:
        packed.append(curr_byte)
    
    return bytes(packed)


# Function to unpack bytes back into a bitfield list
def unpack_bitfield(payload, num_pieces):
    bitfield = []
    # Iterate through each byte in the payload
    for byte in payload:
        # Iterate through each bit in the byte, starting from the most sig bit and append to the bitfield list
        for shift in range (7, -1, -1):
            bitfield.append((byte >> shift) & 1)

    return bitfield[:num_pieces]


# Function to check if there are any pieces that the neighbor has that ours doesn't
def has_interesting_piece(my_bitfield, neighbor_bitfield):
    # Iterate through both bitfields and check if neighbor has a piece that ours doesn't
    for my_bit, neighbor_bit in zip(my_bitfield, neighbor_bitfield):
        # If neighbor has piece (neighbor_bit = 1) and we don't(my_bit = 0), then it's interesting
        if neighbor_bit and not my_bit:
            return True
    return False


# Function to store the neighbor's bitfield in the state dict
def store_neighbor_bitfield(state, peer_id, bitfield):
    with state["lock"]:
        state["neighbor_bitfields"][peer_id] = bitfield


# Function to update the neighbor's bitfield when receiving a HAVE message
def update_neighbor_have(state, peer_id, piece_index):
    with state["lock"]:
        # If neighbor's bitfield doesn't exist yet, initialize it with zeros
        if peer_id not in state["neighbor_bitfields"]:
            size = len(state["my_bitfield"])
            state["neighbor_bitfields"][peer_id] = [0] * size
        
        # Set the bit for piece index to 1 to show neighbor has that piece
        state["neighbor_bitfields"][peer_id][piece_index] = 1


# Function to see if we should send an INTERESTED or NOT_INTERESTED message based on the neighbor's and our bitfield
def send_interest_decision(connection, state, peer_id):
    with state["lock"]:
        # Make copies of the bitfields and interest state to minimize time holding the lock
        my_bitfield = list(state["my_bitfield"])
        neighbor_bitfield = state["neighbor_bitfields"].get(peer_id)
        last_interest = state["interest_state"].get(peer_id)

    # Check if neighbor's bitfield is available, if not then can't make a decision yet
    if neighbor_bitfield is None:
        return
    
    interested = has_interesting_piece(my_bitfield, neighbor_bitfield)
    # Check if our interest state changed since last time, if not then no need to send a message
    if last_interest is not None and last_interest == interested:
        return
    
    # If interested then send INTERESTED message
    if interested:
        send_msg(connection, MsgType.INTERESTED)
    
    # Else send NOT_INTERESTED message
    else:
        send_msg(connection, MsgType.NOT_INTERESTED)
    
    # Update the interest state for this peer in the state dict
    with state["lock"]:
        state["interest_state"][peer_id] = interested


# Main function to handle new bitfield messages, update state, and send interest decision
def handle_bitfield(connection, state, peer_id, payload, num_pieces):
    neighbor_bitfield = unpack_bitfield(payload, num_pieces)
    store_neighbor_bitfield(state, peer_id, neighbor_bitfield)
    send_interest_decision(connection, state, peer_id)


# Function to handle HAVE messages, update neighbor's bitfield, and send interest decision
def handle_have(connection, state, peer_id, payload):
    piece_index = unpack_piece_index(payload)
    update_neighbor_have(state, peer_id, piece_index)
    send_interest_decision(connection, state, peer_id)


# Function to broadcast HAVE message to all connected peers when getting a new piece
def broadcast_have(state, piece_index):
    payload = pack_piece_index(piece_index)

    # Make a copy of connections to minimize time holding the lock while sending messages
    with state["lock"]:
        connections = list(state["connections"].items())

    # Iterate through all connections and send HAVE message with the piece index payload
    for peer_id, connection in connections:
        try:
            send_msg(connection, MsgType.HAVE, payload)

        # If sending fails, ignore so connection handling code cleans up the state for that peer
        except OSError:
            pass


# Getter function to retrieve our bitfield from the state dict
def get_my_bitfield(state):
    with state["lock"]:
        return list(state["my_bitfield"])


# Setter function to update our bitfield in the state dict when we get a new piece
def set_my_piece(state, piece_index):
    with state["lock"]:
        state["my_bitfield"][piece_index] = 1


# Getter function to retrieve neighbor's bitfield from the state dict
def get_neighbor_bitfield(state, peer_id):
    with state["lock"]:
        # If neighbor's bitfield doesn't exist yet, return None showing info not available yet
        if peer_id not in state["neighbor_bitfields"]:
            return None
        return list(state["neighbor_bitfields"][peer_id])
