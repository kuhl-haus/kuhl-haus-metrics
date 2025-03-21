import pickle
import socket
import struct
from typing import List


class CarbonPoster:
    server_ip: str
    pickle_port: int

    def __init__(self, server_ip: str, pickle_port: int):
        self.server_ip = server_ip
        self.pickle_port = pickle_port

    def post_metrics(self, metrics: List[tuple]):
        payload = pickle.dumps(metrics, protocol=2)
        header = struct.pack("!L", len(payload))
        message = header + payload
        with socket.socket() as sock:
            sock.connect((self.server_ip, self.pickle_port))
            sock.sendall(message)
