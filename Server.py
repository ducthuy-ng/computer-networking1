import socket
import sys

from ServerWorker import ServerWorker


class Server:

    def main(self):
        try:
            SERVER_PORT = int(sys.argv[1])
        except:
            print("[Usage: Server.py Server_port]\n")
        rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        rtsp_socket.bind(('', SERVER_PORT))
        rtsp_socket.listen(5)

        # Receive client info (address,port) through RTSP/TCP session
        while True:
            clientInfo = {}
            clientInfo['rtsp_socket'] = rtsp_socket.accept()
            ServerWorker(clientInfo).run()


if __name__ == "__main__":
    (Server()).main()
