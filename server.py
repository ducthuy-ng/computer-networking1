import configparser
import logging
import pathlib
import socket

from server_worker import ServerWorker


class Server:
    def __init__(self, hostname: str = None, server_port: int = None):
        self.config_parser: configparser.ConfigParser = configparser.ConfigParser()
        self.config_parser.read("./config/server.cfg")
        self.rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.logger = logging.getLogger("streaming-app.server")

    def run(self):
        self.rtsp_socket.bind((self.config_parser['Server']['hostname'],
                               self.config_parser.getint('Server', 'server_port')))
        self.rtsp_socket.listen(self.config_parser.getint('Socket', 'backlog'))

        self.logger.info("Server Started")

        # Receive client info (address, port) through RTSP/TCP session
        try:
            while True:
                connection_socket, client_addr = self.rtsp_socket.accept()
                self.logger.debug(f"Client {client_addr[0]}:{client_addr[1]} has connected")
                ServerWorker(connection_socket, client_addr,
                             pathlib.Path(self.config_parser['Server']['video_folder'])).start()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    # Setting up server logger
    logger = logging.getLogger("streaming-app.server")
    logger.setLevel(logging.DEBUG)

    stream_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')
    stream_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)

    server = Server()
    server.run()
