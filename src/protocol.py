"""
Citations:
https://beej.us/guide/bgnet/ - recv(), TCP sockets, struct packing/unpacking
https://docs.python.org/3/library/ - socket, sendall, bigendian, struct
https://eli.thegreenplace.net/2011/08/02/length-prefix-framing-for-protocol-buffers - length prefix framing
"""


import struct
from constants import MsgType, HANDSHAKE_HEADER, HANDSHAKE_ZEROS, HANDSHAKE_LEN

# Handshake Handling
def build_handshake(peer_id: int):
    # 18 bytes header + 10 bytes zeros + 4 bytes peer_id (In big-endian)
    return HANDSHAKE_HEADER + HANDSHAKE_ZEROS + struct.pack('>I', peer_id)

def parse_handshake(data: bytes):
    # Check that the handshake has the correct total size
    if len(data) != HANDSHAKE_LEN:
        raise ValueError("Invalid handshake length")
    
    # Extract each section of handshake
    header = data[:len(HANDSHAKE_HEADER)]
    zeros = data[len(HANDSHAKE_HEADER):len(HANDSHAKE_HEADER) + len(HANDSHAKE_ZEROS)]
    peer_id_bytes = data[len(HANDSHAKE_HEADER) + len(HANDSHAKE_ZEROS):len(HANDSHAKE_HEADER) + len(HANDSHAKE_ZEROS) + 4]

    # Validate header
    if header != HANDSHAKE_HEADER:
        raise ValueError("Invalid handshake header")
    
    # Validate zeros
    if zeros != HANDSHAKE_ZEROS:
        raise ValueError("Invalid handshake zeros") 
    

    # Convert final 4 bytes into peer_id
    peer_id = struct.unpack('>I', peer_id_bytes)[0]
    return peer_id

def build_msg(msg_type: MsgType, payload: bytes = b''):
    # Message format: 4 bytes length (big-endian) + 1 byte type + payload
    # msg_len = 1 byte for type + payload length
    msg_len = 1 + len(payload)
    msg = struct.pack(">I", msg_len)
    msg += struct.pack("B", int(msg_type))
    msg += payload

    return msg

def recv_extract(sock, num_bytes: int):
    # Helper function to receive exactly num_bytes from socket
    data = b''

    # Keep receiving until we have required num bytes
    while len(data) < num_bytes:
        packet = sock.recv(num_bytes - len(data))

        # If recv returns empty, then connection is closed
        if not packet:
            raise ConnectionError("Socket connection closed")

        # Append received packet to data
        data += packet
    return data

def recv_handshake(sock):
    # Receive handshake data
    data = recv_extract(sock, HANDSHAKE_LEN)
    return parse_handshake(data)

def recv_message(sock):
    # Receive 4 bytes for msg_len
    length_data = recv_extract(sock, 4)
    msg_len = struct.unpack(">I", length_data)[0]

    # msg_len must be at least 1 byte
    if msg_len < 1:
        raise ValueError("Invalid message length")

    # Receive rest of msg based on msg_len
    msg_data = recv_extract(sock, msg_len)

    # First byte of msg_data is the msg_type
    msg_type = MsgType(msg_data[0])

    # The rest is payload
    payload = msg_data[1:]

    return msg_type, payload

def send_handshake(sock, peer_id: int):
    # Build handshake message
    handshake_msg = build_handshake(peer_id)
    # Send handshake message to socket
    sock.sendall(handshake_msg)

def send_msg(sock, msg_type: MsgType, payload: bytes = b''):
    # Build message
    msg = build_msg(msg_type, payload)
    # Send message to socket
    sock.sendall(msg)

def pack_piece_index(index: int):
    # Pack piece index as 4 bytes big-endian
    return struct.pack(">I", index)

def unpack_piece_index(payload: bytes):
    # Payload for HAVE and REQUEST messages are exactly 4 bytes
    if len(payload) != 4:
        raise ValueError("Invalid piece index payload length")
    
    # Unpack 4 bytes big-endian to get piece index
    return struct.unpack(">I", payload)[0]

def build_have_msg(piece_index: int):
    # Build HAVE message with piece index as payload
    return build_msg(MsgType.HAVE, pack_piece_index(piece_index))

def build_request_msg(piece_index: int):
    # Build REQUEST message with piece index as payload
    return build_msg(MsgType.REQUEST, pack_piece_index(piece_index))

def expected_bitfield_len(num_pieces: int):
    # Calculate expected bitfield length in bytes for given number of pieces
    return (num_pieces + 7) // 8

def validate_bitfield(payload: bytes, num_pieces: int):
    # Validate that bitfield payload has correct length for given number of pieces
    if len(payload) != expected_bitfield_len(num_pieces):
        raise ValueError("Invalid bitfield length")
    return True

def msg_name(msg_type: MsgType):
    # Helper function to get string name of message type
    return msg_type.name

def is_control_msg(msg_type: MsgType):
    # Control messages: CHOKE, UNCHOKE, INTERESTED, NOT_INTERESTED
    return msg_type in {MsgType.CHOKE, MsgType.UNCHOKE, MsgType.INTERESTED, MsgType.NOT_INTERESTED}

def is_index_msg(msg_type: MsgType):
    # Index messages: HAVE, REQUEST
    return msg_type in {MsgType.HAVE, MsgType.REQUEST}

def parse_index_payload(msg_type: MsgType, payload: bytes):
    # Parse piece index from payload for HAVE and REQUEST messages
    if not is_index_msg(msg_type):
        raise ValueError("Message type does not contain piece index")
    return unpack_piece_index(payload)

def has_payload(msg_type: MsgType):
    # Only PIECE and BITFIELD messages have payloads
    return msg_type in {MsgType.PIECE, MsgType.BITFIELD}
