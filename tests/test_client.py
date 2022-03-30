import random
import tkinter as tk

import pytest

from client import Client


def mock_socket_socket(socket_type, socket_stream_type):
    return MockSocket()


class MockSocket:
    def __init__(self):
        self.session_id = random.randint(100000, 999999)

    def connect(self, addr):
        pass

    def sendall(self, data):
        print(data)

    def settimeout(self, time):
        pass

    def bind(self, addr):
        pass

    def getsockname(self):
        return 'localhost', random.randint(100000, 999999)

    def recv(self, byte_size):
        return f"RTSP/1.0 200 OK\nCSeq: 1\nSession: {self.session_id}".encode()


@pytest.fixture
def generate_client(mocker, scope="function"):
    mocker.patch('socket.socket', mock_socket_socket)
    root = tk.Toplevel()

    client = Client(root)
    root.update()
    return client


def test_basic_functional(mocker):
    mocker.patch('socket.socket', mock_socket_socket)
    root = tk.Tk()
    client = Client(root)
    root.update()

    client.setup_video()
    assert client.sequence_number == 1
    assert client.session_id == client.connection_socket.session_id

    client.play_video()
    assert client.sequence_number == 2

    client.pause_video()
    assert client.sequence_number == 3

    client.stop_video()
    assert client.sequence_number == 4

    # Tearing down root
    del client, root


def test_duplicate_action_should_not_count(generate_client):
    generate_client.setup_video()
    generate_client.setup_video()
    assert generate_client.sequence_number == 1

    generate_client.play_video()
    generate_client.play_video()
    assert generate_client.sequence_number == 2

    generate_client.pause_video()
    generate_client.pause_video()
    assert generate_client.sequence_number == 3

    generate_client.stop_video()
    generate_client.stop_video()
    assert generate_client.sequence_number == 4


def test_invalid_state_transition_should_not_count(generate_client):
    # =========================================================
    # Currently, state is ready INIT
    # =========================================================
    generate_client.pause_video()
    assert generate_client.session_id == 0
    assert generate_client.sequence_number == 0

    generate_client.play_video()
    assert generate_client.session_id == 0
    assert generate_client.sequence_number == 0

    # =========================================================
    # Change state to READY
    # =========================================================
    generate_client.setup_video()

    generate_client.setup_video()
    assert generate_client.sequence_number == 1

    generate_client.pause_video()
    assert generate_client.sequence_number == 1

    # =========================================================
    # Change state to PLAYING
    # =========================================================
    generate_client.play_video()

    generate_client.play_video()
    assert generate_client.sequence_number == 2

    generate_client.setup_video()
    assert generate_client.sequence_number == 2
