from protocol import *
from constants import MsgType
import socket


def test_handshake():
    peer_id = 1001
    handshake = build_handshake(peer_id)
    parsed_id = parse_handshake(handshake)

    assert len(handshake) == 32
    assert parsed_id == peer_id
    print("Handshake test passed")


def test_message():
    payload = b"why hello there"
    msg = build_msg(MsgType.BITFIELD, payload)

    msg_len = int.from_bytes(msg[:4], byteorder="big")
    msg_type = msg[4]
    msg_payload = msg[5:]

    assert msg_len == 1 + len(payload)
    assert msg_type == MsgType.BITFIELD
    assert msg_payload == payload
    print("Message build test passed")


def test_piece_index():
    index = 7
    packed = pack_piece_index(index)
    unpacked = unpack_piece_index(packed)

    assert unpacked == index
    print("Piece index test passed")


def test_bitfield():
    assert expected_bitfield_len(1) == 1
    assert expected_bitfield_len(8) == 1
    assert expected_bitfield_len(9) == 2
    assert validate_bitfield(b"\x00", 8) is True
    print("Bitfield helper test passed")


def test_socket_roundtrip():
    sock1, sock2 = socket.socketpair()

    try:
        send_handshake(sock1, 1002)
        received_id = recv_handshake(sock2)
        assert received_id == 1002

        send_msg(sock1, MsgType.INTERESTED, b"")
        msg_type, payload = recv_message(sock2)
        assert msg_type == MsgType.INTERESTED
        assert payload == b""

        send_msg(sock1, MsgType.HAVE, pack_piece_index(4))
        msg_type, payload = recv_message(sock2)
        assert msg_type == MsgType.HAVE
        assert unpack_piece_index(payload) == 4

        print("Socket roundtrip test passed")

    finally:
        sock1.close()
        sock2.close()


if __name__ == "__main__":
    test_handshake()
    test_message()
    test_piece_index()
    test_bitfield()
    test_socket_roundtrip()
    print("All protocol tests passed")