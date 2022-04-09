import configparser
import datetime
import io
import logging
import math
import pathlib
import socket

from PIL import Image

from server_worker import ServerWorker
from video_stream import VideoStream


class Server:
    def __init__(self, hostname: str = None, server_port: int = None):
        self.config_parser: configparser.ConfigParser = configparser.ConfigParser()
        self.config_parser.read("./config/server.cfg")
        self.rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.logger = logging.getLogger("streaming-app.server")

    def run(self):
        # Generate video info files to reduce computation
        self.generate_video_infos()

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

    def generate_video_infos(self):
        video_path: pathlib.Path = pathlib.Path(self.config_parser['Server']['video_folder'])
        for video_file in video_path.iterdir():
            # Skipping non-video files
            if video_file.suffix.lower() != ".mjpeg":
                continue

            # Skip if info file has existed
            info_file_path: pathlib.Path = video_file.with_suffix(".info")
            if info_file_path.exists():
                continue

            info_file_path.touch()
            with open(info_file_path, 'r+') as info_file:
                info_file.write(f"filename={video_file.name}\n")

                stream = VideoStream(video_file)
                image = Image.open(io.BytesIO(stream.next_frame()))
                info_file.write(f"resolution={image.size[0]}x{image.size[1]}\n")

                while stream.next_frame():
                    pass

                duration = datetime.timedelta(seconds=math.ceil(stream.frame_nbr() * 0.05))
                info_file.write(f"duration={duration}\n")


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
