import logging
import pathlib
import socket

from server_worker import ServerWorker


class Server:
    def __init__(self, hostname: str = None, server_port: int = None):
        self.hostname: str = hostname if hostname else '0.0.0.0'
        self.server_port: int = server_port if server_port else 2103
        self.video_folder: pathlib.Path = pathlib.Path("./videos")
        self.rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def run(self):
        self.rtsp_socket.bind((self.hostname, self.server_port))
        self.rtsp_socket.listen(5)

        # Receive client info (address, port) through RTSP/TCP session
        try:
            while True:
                connection_socket, client_addr = self.rtsp_socket.accept()
                ServerWorker(connection_socket, client_addr, self.video_folder).run()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    server = Server()
    server.run()
