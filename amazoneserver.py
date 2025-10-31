import socket
import struct
import threading
import time

AMAZONE_PORT = 22000

TYPE_MAP = {"A": 8, "AAAA": 4, "CNAME": 2, "NS": 1}
TYPE_MAP_REV = {v: k for k, v in TYPE_MAP.items()}

def print_rr_table(rr_table):
    print("record_no,name,type,result,ttl,static")
    for r in rr_table:
        ttl = "None" if r["static"] else str(r["ttl"])
        print(f'{r["record_no"]},{r["name"]},{r["type"]},{r["result"]},{ttl},{1 if r["static"] else 0}')
    print("")

class AmazoneServer:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', AMAZONE_PORT))
        self.rr_table = []
        self.record_counter = 0
        # seed some static records for amazone domain
        self.rr_table.append({
            "record_no": self.record_counter,
            "name": "shop.amazone.com",
            "type": "A",
            "result": "3.33.147.88",
            "ttl": None,
            "static": True
        })
        self.rr_table.append({
            "record_no": self.record_counter,
            "name": "cloud.amazone.com",
            "type": "A",
            "result": "15.197.140.28",
            "ttl": None,
            "static": True
        })
        self.record_counter += 1

    def listen(self):
        print("[amazone] Listening on port", AMAZONE_PORT)
        while True:
            data, addr = self.sock.recvfrom(4096)
            if not data:
                continue
            txid, flags = struct.unpack("!IB", data[:5])
            if flags == 0:
                qtype = data[5]
                name_len = struct.unpack("!H", data[6:8])[0]
                name = data[8:8+name_len].decode('utf-8')
                print(f"[amazone] Received query for {name} type {qtype} from {addr}")
                # check rr table
                answer = None
                for r in self.rr_table:
                    if r["name"] == name and r["type"] == TYPE_MAP_REV.get(qtype, str(qtype)):
                        answer = r
                        break
                if answer:
                    # send response back
                    self._send_response(txid, addr, answer["name"], TYPE_MAP[answer["type"]], 60, answer["result"])
                    print("[amazone] Sent response (from local RR):")
                    print_rr_table(self.rr_table)
                else:
                    # not found
                    self._send_response(txid, addr, name, qtype, 0, "Record not found")
                    print("[amazone] Record not found - responded NOT FOUND")
            # ignore if flags==1 (shouldn't happen)

    def _send_response(self, txid, addr, name, atype, ttl, result):
        name_b = name.encode('utf-8')
        result_b = result.encode('utf-8')
        flags = 1
        msg = struct.pack("!IBB H", txid, flags, atype, len(name_b)) + name_b + struct.pack("!I H", ttl, len(result_b)) + result_b
        self.sock.sendto(msg, addr)


def main():
    server = AmazoneServer()
    server.listen()


if __name__ == '__main__':
    main()