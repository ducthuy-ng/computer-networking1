import multiprocessing
import socket
import time
from http.client import OK

import pytest

from server import Server

HOST = '127.0.0.1'
SERVER_PORT = 3000
CLIENT_PORT = 25000

SETUP = 'SETUP'
PLAY = 'PLAY'
PAUSE = 'PAUSE'
TEARDOWN = 'TEARDOWN'


def start_server_process(server):
    server.run()


@pytest.fixture(autouse=True, scope='module')
def setup_server(request):
    server = Server(server_port=SERVER_PORT)

    server_process = multiprocessing.Process(target=start_server_process, args=(server,))
    server_process.start()

    # Wait for server_process to fully start
    time.sleep(1)
    request.addfinalizer(lambda: server_process.kill())


def send_request(connection_socket: socket.socket, port, action, file, c_seq, session):
    req = f"{action} {file} RTSP/1.0\nCSeq: {c_seq}\n"

    if action == SETUP:
        req += f"Transport: RTP/UDP; client_port= {port}\n"
    else:
        req += f"Session: {session}\n"

    connection_socket.sendall(str.encode(req))
    data = connection_socket.recv(1024).decode("utf-8")
    print(data)
    if int(data.split('\n')[0].split(' ')[1]) == OK:
        session = int(data.split('\n')[2].removeprefix('Session: '))
    return data, session


def build_and_run_test(actions, file, server_port=SERVER_PORT):
    ssid = 0  # session id
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(('', server_port))
        for idx, action in enumerate(actions, 1):
            response, ssid = send_request(s, CLIENT_PORT, action, file, idx, ssid)
            if response != f'RTSP/1.0 200 OK\nCSeq: {idx}\nSession: {ssid}\n':
                s.close()
                return False
        s.close()
    return True


def test_is_server_listening():
    file = 'movie.Mjpeg'  # file name to stream
    actions = [SETUP]  # a set of actions

    assert build_and_run_test(actions, file, SERVER_PORT)


def test_setup():
    file = 'movie.Mjpeg'  # file name to stream
    actions = [SETUP]  # a set of actions

    assert build_and_run_test(actions, file)


def test_play():
    file = 'movie.Mjpeg'
    actions = [SETUP, PLAY]

    assert build_and_run_test(actions, file)


def test_pause():
    file = 'movie.Mjpeg'
    actions = [SETUP, PLAY, PAUSE]

    assert build_and_run_test(actions, file)


def test_teardown():
    file = 'movie.Mjpeg'
    actions = [SETUP, PLAY, TEARDOWN]

    assert build_and_run_test(actions, file)


def test_action_sequence1():
    file = 'movie.Mjpeg'
    actions = [SETUP, TEARDOWN]

    assert build_and_run_test(actions, file)


def test_action_sequence2():
    file = 'movie.Mjpeg'
    actions = [SETUP, PLAY, TEARDOWN]

    assert build_and_run_test(actions, file)


def test_action_sequence3():
    file = 'movie.Mjpeg'
    actions = [SETUP, PLAY, PAUSE, TEARDOWN]

    assert build_and_run_test(actions, file)


def test_action_sequence4():
    file = 'movie.Mjpeg'
    actions = [SETUP, PLAY, PAUSE, PLAY, TEARDOWN]

    assert build_and_run_test(actions, file)


def test_action_sequence5():
    file = 'movie.Mjpeg'
    actions = [SETUP, PLAY, PAUSE, TEARDOWN, SETUP]

    assert build_and_run_test(actions, file)
