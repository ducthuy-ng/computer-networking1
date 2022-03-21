import time
from typing import Union

HEADER_SIZE = 12


class RtpPacket:
    header = bytearray(HEADER_SIZE)

    def __init__(self):
        self.header: bytearray = bytearray()
        self.payload: bytearray = bytearray()

    @staticmethod
    def encode(version: int, padding: int, extension: int, cc: int, marker: int,
               payload_type: int, seq_num: int, ssrc: int, payload: bytearray) -> bytearray:
        """Encode the RTP packet with header fields and payload."""
        header = bytearray(HEADER_SIZE)

        header[0] |= version << 6
        header[0] |= padding << 5
        header[0] |= extension << 4
        header[0] |= cc

        header[1] |= marker << 7
        header[1] |= payload_type

        if seq_num >= (1 << 16):
            raise OverflowError("Sequence number must in [0 - 65535]")

        header[2] = seq_num >> 8
        header[3] = (0xff & seq_num)

        timestamp = int(time.time()).to_bytes(length=4, byteorder='big')
        header[4:8] = timestamp

        header[8:12] = ssrc.to_bytes(length=4, byteorder='big')

        return header + payload

    def decode(self, byte_stream: Union[bytes, bytearray]):
        """Decode the RTP packet."""
        self.header = bytearray(byte_stream[:HEADER_SIZE])
        self.payload = byte_stream[HEADER_SIZE:]

    def get_version(self):
        """Return RTP version."""
        return int(self.header[0] >> 6)

    def get_seq_num(self):
        """Return sequence (frame) number."""
        return int(self.header[2] << 8 | self.header[3])

    def get_timestamp(self):
        """Return timestamp."""
        timestamp = self.header[4] << 24 | self.header[5] << 16 | self.header[6] << 8 | self.header[7]
        return int(timestamp)

    def get_payload_type(self):
        """Return payload type."""
        pt = self.header[1] & 127
        return int(pt)

    def get_payload(self):
        """Return payload."""
        return self.payload

    def get_packet(self):
        """Return RTP packet."""
        return self.header + self.payload
