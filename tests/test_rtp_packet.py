import random

import pytest

from RtpPacket import RtpPacket

PAYLOAD_MAX_SIZE = 200


def test_encoding_byte_0():
    result: bytearray = RtpPacket.encode(0, 0, 0, 0, 0, 0, 0, 0, bytearray(5))
    assert result[0] == 0

    result: bytearray = RtpPacket.encode(0, 1, 0, 0, 0, 0, 0, 0, bytearray(5))
    assert result[0] == 0b00100000
    result: bytearray = RtpPacket.encode(2, 0, 0, 0, 0, 0, 0, 0, bytearray(5))
    assert result[0] == 0b10000000

    result: bytearray = RtpPacket.encode(0, 1, 0, 0, 0, 0, 0, 0, bytearray(5))
    assert result[0] == 0b00100000

    result: bytearray = RtpPacket.encode(0, 0, 1, 0, 0, 0, 0, 0, bytearray(5))
    assert result[0] == 0b00010000

    result: bytearray = RtpPacket.encode(0, 0, 0, 15, 0, 0, 0, 0, bytearray(5))
    assert result[0] == 0b00001111


def test_encoding_byte_1():
    result: bytearray = RtpPacket.encode(0, 0, 0, 0, 0, 0, 0, 0, bytearray(5))
    assert result[1] == 0

    result: bytearray = RtpPacket.encode(0, 0, 0, 0, 1, 0, 0, 0, bytearray(5))
    assert result[1] == 0b10000000

    result: bytearray = RtpPacket.encode(0, 0, 0, 0, 0, 26, 0, 0, bytearray(5))
    assert result[1] == 0b00011010


def test_encoding_byte_2_3():
    result: bytearray = RtpPacket.encode(2, 1, 1, 1, 1, 26, 0, 0, bytearray(5))
    assert result[2] == 0
    assert result[3] == 0

    result: bytearray = RtpPacket.encode(2, 1, 1, 1, 1, 26, 50000, 0, bytearray(5))
    assert result[2] == 0b11000011
    assert result[3] == 0b01010000

    result: bytearray = RtpPacket.encode(2, 1, 1, 1, 1, 26, 65535, 0, bytearray(5))
    assert result[2] == 0b11111111
    assert result[3] == 0b11111111

    with pytest.raises(OverflowError) as overflow_exception:
        result: bytearray = RtpPacket.encode(2, 1, 1, 1, 1, 26, 65536, 0, bytearray(5))


def test_encoding_byte_4_7():
    import time

    timestamp = int(time.time())
    result: bytearray = RtpPacket.encode(2, 1, 1, 1, 1, 26, 65535, 0, bytearray(5))

    assert int(result[4:8].hex(), 16) == timestamp


def test_encoding_byte_8_11():
    for i in range(10):
        random_number: int = random.randint(0, 2 ** 32 - 1)
        result: bytearray = RtpPacket.encode(2, 0, 0, 0, 0, 26, 5, random_number, bytearray(5))

        assert int(result[8:12].hex(), 16) == random_number


def test_encoding_payload():
    payload: bytearray = bytearray(random.randbytes(PAYLOAD_MAX_SIZE))
    result: bytearray = RtpPacket.encode(2, 0, 0, 0, 0, 26, 5, 4, payload)

    assert result[12:] == payload
