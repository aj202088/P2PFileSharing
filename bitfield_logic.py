import threading
import random
from protocol import pack_piece_index, unpack_piece_index
from constants import MsgType

'''
    CITATIONS:
        https://realpython.com/python-thread-lock/ - threading lock usage
        https://www.bittorrent.org/beps/bep_0003.html - BitTorrent peer wire protocol reference
        https://github.com/bittorrent/bittorrent.org/blob/master/beps/bep_0052.rst - bitfield layout and interested/not interested message reference
        https://wiki.theory.org/BitTorrentSpecification - detailed BitTorrent message behavior reference
        https://github.com/webtorrent/bittorrent-protocol/blob/master/README.md - BitTorrent peer wire protocol library showing handshake, bitfield, have, and peer state handling implementation

'''


# Logic for handling bitfield messages and maintaining the state of which pieces have been downloaded
def create_bitfield_state(my_bitfield):
    return {
        "my_bitfield": list(my_bitfield),
        "neighbor_bitfields": {},
        "prev_pref_neighbors": set(),
        "interest_state": {},
        "requested_pieces": set(),
        "lock": threading.Lock()
    }


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

    # If there are remaining bits not filling a full byte, append the last byte
    if (len(bitfield) % 8) != 0:
        packed.append(curr_byte)
    return bytes(packed)


# Function to unpack bytes back into a bitfield list
def unpack_bitfield(payload, num_pieces):
    bitfield = []

    # Iterate through each byte in the payload
    for byte in payload:
        # Iterate through each bit in the byte, starting from the most sig bit and append to the bitfield list
        for shift in range(7, -1, -1):
            bitfield.append((byte >> shift) & 1)

    return bitfield[:num_pieces]


# Function to store the neighbor's bitfield in the state dict
def store_neighbor_bitfield(state, peer_id, bitfield):
    with state["lock"]:
        state["neighbor_bitfields"][peer_id] = list(bitfield)


# Function to update the neighbor's bitfield when receiving a HAVE message
def update_neighbor_have(state, peer_id, piece_index):
    with state["lock"]:
        # If neighbor's bitfield doesn't exist yet, initialize it with zeros
        if peer_id not in state["neighbor_bitfields"]:
            size = len(state["my_bitfield"])
            state["neighbor_bitfields"][peer_id] = [0] * size

        # Set the bit for piece index to 1 to show neighbor has that piece
        if 0 <= piece_index < len(state["neighbor_bitfields"][peer_id]):
            state["neighbor_bitfields"][peer_id][piece_index] = 1


# Function to check if we should be interested in this neighbor based on their bitfield and our bitfield
def has_interesting_piece(my_bitfield, neighbor_bitfield):
    # Iterate through both bitfields and check if neighbor has a piece that ours doesn't
    for my_piece, neighbor_piece in zip(my_bitfield, neighbor_bitfield):
        # If neighbor has piece (neighbor_piece = 1) and we don't(my_piece = 0), then it's interesting
        if my_piece == 0 and neighbor_piece == 1:
            return True
    return False


# Function to determine if we should be interested in this neighbor based on their bitfield and our bitfield
def get_interest_decision(state, peer_id):
    with state["lock"]:
        # Save copies of our bitfield and neighbor's bitfield to work with outside the lock to minimize time holding the lock
        my_bitfield = list(state["my_bitfield"])
        neighbor_bitfield = state["neighbor_bitfields"].get(peer_id)

    # If we do not know the neighbor's bitfield yet, do not show interest yet
    if neighbor_bitfield is None:
        return False
    
    for my_piece, neighbor_piece in zip(my_bitfield, neighbor_bitfield):
        if my_piece == 0 and neighbor_piece == 1:
            return True

    return has_interesting_piece(my_bitfield, neighbor_bitfield)


# Function to get the last interest state we sent to this neighbor from the state dict
def get_last_interest_state(state, peer_id):
    # Read the last interest state stored for neighbor
    with state["lock"]:
        return state["interest_state"].get(peer_id)


# Function to update the last interest state sent to neighbor in the state dict
def set_last_interest_state(state, peer_id, interested):
    # Save the last interest decision sent
    with state["lock"]:
        state["interest_state"][peer_id] = interested


# Helper function to determine if a new interest message should be sent
def get_interest_message(state, peer_id):
    interested = get_interest_decision(state, peer_id)
    last_interest = get_last_interest_state(state, peer_id)

    # If this is the first decision or the decision changed, return the correct message type
    if last_interest is None or last_interest != interested:
        set_last_interest_state(state, peer_id, interested)

        # If interested then return INTERESTED message type
        if interested:
            return MsgType.INTERESTED
        # Else return NOT_INTERESTED message type
        return MsgType.NOT_INTERESTED

    return None


# Main function to handle new bitfield messages, update state, and determine interest decision
def handle_bitfield(state, peer_id, payload, num_pieces):
    neighbor_bitfield = unpack_bitfield(payload, num_pieces)
    store_neighbor_bitfield(state, peer_id, neighbor_bitfield)
    return get_interest_message(state, peer_id)


# Function to handle HAVE messages, update neighbor's bitfield, and determine interest decision
def handle_have(state, peer_id, payload):
    piece_index = unpack_piece_index(payload)
    update_neighbor_have(state, peer_id, piece_index)
    return piece_index, get_interest_message(state, peer_id)


# Helper function to build a HAVE message payload from a piece index
def build_have_payload(piece_index):
    return pack_piece_index(piece_index)


# Getter function to retrieve our bitfield from the state dict
def get_my_bitfield(state):
    with state["lock"]:
        return list(state["my_bitfield"])


# Setter function to update our bitfield in the state dict when getting a new piece
def set_my_piece(state, piece_index):
    with state["lock"]:
        # If piece index is valid, set the bit for that piece index to 1 to show piece received
        if 0 <= piece_index < len(state["my_bitfield"]):
            state["my_bitfield"][piece_index] = 1


# Getter function to retrieve neighbor's bitfield from the state dict
def get_neighbor_bitfield(state, peer_id):
    with state["lock"]:
        # If neighbor's bitfield doesn't exist yet, return None showing info not available yet
        if peer_id not in state["neighbor_bitfields"]:
            return None
        return list(state["neighbor_bitfields"][peer_id])


# Helper function to re-check all neighbors after gaining a new piece
def reevaluate_all_interest(state):
    updates = []

    # Get a list of all neighbor IDs
    with state["lock"]:
        peer_ids = list(state["neighbor_bitfields"].keys())

    # For each neighbor, check if interested
    for peer_id in peer_ids:
        msg_type = get_interest_message(state, peer_id)
        # If the interest decision changed, add to updates list
        if msg_type is not None:
            updates.append((peer_id, msg_type))

    return updates


# Randomly picks a piece that the remote peer has, we don't have, and isn't already in-flight
# Returns the piece index, or None if no candidates exist
# CITATION: Random piece selection per project spec 'request and piece' section
def pick_piece_to_request(state, peer_id):
    with state["lock"]:
        my_bf = state["my_bitfield"]
        neighbor_bf = state["neighbor_bitfields"].get(peer_id)
        requested = state["requested_pieces"]

        if neighbor_bf is None:
            return None

        # Build list of candidate pieces: remote has it, we don't, not in-flight
        candidates = [
            i for i, (mine, theirs) in enumerate(zip(my_bf, neighbor_bf))
            if mine == 0 and theirs == 1 and i not in requested
        ]

    if not candidates:
        return None

    return random.choice(candidates)


# Marks a piece index as in-flight so other connections don't also request it
def mark_piece_requested(state, piece_index):
    with state["lock"]:
        state["requested_pieces"].add(piece_index)


# Removes a piece from in-flight tracking when received or when choked
def unmark_piece_requested(state, piece_index):
    with state["lock"]:
        state["requested_pieces"].discard(piece_index)


# Returns how many pieces we currently have based on our bitfield
def count_my_pieces(state):
    with state["lock"]:
        return sum(state["my_bitfield"])


# Returns True if we have all pieces based on our bitfield, False otherwise
def has_complete_file(state):
    with state["lock"]:
        return all(state["my_bitfield"])
