from enum import Enum
from typing import List


class RtspResponse:
    def __init__(self, data: str):
        if data == "":
            raise ConnectionError
        self.content = data.encode("utf-8")
        self.line: List[str] = data.split('\n')

        self.status_code: int = int(self.line[0].split(' ')[1])
        self.sequence_number: int = int(self.line[1].split(' ')[1])

    def get_session_id(self) -> int:
        if self.line[2].startswith("Session:"):
            return int(self.line[2].split(' ')[1])
        else:
            return 0

    def get_other_line(self) -> List[str]:
        external_field_index = 2
        if self.line[2].startswith("Session:"):
            external_field_index = 3

        return self.line[external_field_index:]


class ClientState(Enum):
    INIT = 0
    READY = 1
    PLAYING = 2
