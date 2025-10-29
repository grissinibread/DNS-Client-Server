import errno
import socket
import sys
import threading
import time
import struct
import itertools
import shlex

# Constants
LOCAL_DNS_ADDR = ("127.0.0.1", 21000)

FLAG_QUERY = 0
FLAG_RESPONSE = 1


class DNSTypes:
    name_to_code = {"A": 0b1000, "AAAA": 0b0100, "CNAME": 0b0010, "NS": 0b0001}
    code_to_name = {code: name for name, code in name_to_code.items()}

    @staticmethod
    def get_type_code(type_name: str):
        return DNSTypes.name_to_code.get(type_name.upper(), None)

    @staticmethod
    def get_type_name(type_code: int):
        return DNSTypes.code_to_name.get(type_code, None)


# UDP wrapper

class UDPConnection:
    def __init__(self, timeout: int = 5):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(timeout)

    def send_message(self, data: bytes, address: tuple[str, int]):
        self.socket.sendto(data, address)

    def receive_message(self):
        data, addr = self.socket.recvfrom(4096)
        return data, addr

    def close(self):
        self.socket.close()


# Client RR table with TTL

class ClientRRTable:
    def __init__(self):
        self.records = []
        self.record_number = 0
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self.__decrement_ttl, daemon=True)
        self.thread.start()

    def add_record(self, name: str, type_name: str, result: str, ttl: int = 60, static: bool = False):
        with self.lock:
            for r in self.records:
                if r["name"] == name and r["type"] == type_name:
                    r["result"] = result
                    r["ttl"] = None if static else int(ttl)
                    r["static"] = static
                    return
            rec = {
                "record_no": self.record_number,
                "name": name,
                "type": type_name,
                "result": result,
                "ttl": None if static else int(ttl),
                "static": static
            }
            self.records.append(rec)
            self.record_number += 1

    def get_record(self, name: str, type_name: str):
        with self.lock:
            for r in self.records:
                if r["name"] == name and r["type"] == type_name:
                    if (not r["static"]) and r["ttl"] is not None and r["ttl"] <= 0:
                        return None
                    return r.copy()
            return None

    def display_table(self, title=None):
        with self.lock:
            if title:
                print(title)
            print("record_no,name,type,result,ttl,static")
            for r in self.records:
                ttl_out = "None" if r["static"] else str(r["ttl"])
                static_flag = 1 if r["static"] else 0
                print(f'{r["record_no"]},{r["name"]},{r["type"]},{r["result"]},{ttl_out},{static_flag}')
            print("")

    def __decrement_ttl(self):
        while True:
            with self.lock:
                changed = False
                for r in self.records:
                    if not r["static"] and r["ttl"] is not None:
                        r["ttl"] -= 1
                        if r["ttl"] < 0:
                            changed = True
                if changed:
                    self.__remove_expired_records()
            time.sleep(1)

    def __remove_expired_records(self):
        new_list = []
        for r in self.records:
            if r["static"] or (r["ttl"] is not None and r["ttl"] > 0):
                new_list.append(r)
        for i, r in enumerate(new_list):
            r["record_no"] = i
        self.records = new_list
        self.record_number = len(new_list)



# Deserialization helpers
def serialize_query(txid: int, qtype_code: int, name: str) -> bytes:
    name_b = name.encode("utf-8")
    return struct.pack("!IBB H", txid, FLAG_QUERY, qtype_code, len(name_b)) + name_b


def deserialize_response(data: bytes):
    if len(data) < 8:
        return None
    try:
        txid, flags = struct.unpack("!IB", data[:5])
        if flags != FLAG_RESPONSE:
            return None
        atype = data[5]
        name_len = struct.unpack("!H", data[6:8])[0]
        p = 8
        name = data[p:p + name_len].decode("utf-8")
        p += name_len
        ttl = struct.unpack("!I", data[p:p + 4])[0]
        p += 4
        res_len = struct.unpack("!H", data[p:p + 2])[0]
        p += 2
        result = data[p:p + res_len].decode("utf-8")
        return {
            "txid": txid,
            "atype": atype,
            "name": name,
            "ttl": ttl,
            "result": result
        }
    except Exception as e:
        print(f"[client deserialize] Error: {e}")
        return None

# Main logic

def normalize(host: str) -> str:
    return host.strip().lower()


def prompt():
    return "Enter the hostname (or type 'quit' to exit) <hostname> <query type> "


def main():
    rr = ClientRRTable()
    conn = UDPConnection(timeout=5)
    tx_counter = itertools.count(0)

    print("[Client] Ready. Query types: A, AAAA, CNAME, NS")
    rr.display_table("[Client] Initial RR table:")

    try:
        while True:
            line = input(prompt()).strip()
            if not line:
                continue
            if line.lower() == "quit":
                break

            parts = shlex.split(line)
            if len(parts) == 1:
                qname = normalize(parts[0])
                qtype_name = "A"
            else:
                qname = normalize(parts[0])
                qtype_name = parts[1].upper()

            qtype_code = DNSTypes.get_type_code(qtype_name)
            if qtype_code is None:
                print("Type must be one of:", list(DNSTypes.name_to_code.keys()))
                continue

            cached = rr.get_record(qname, qtype_name)
            if cached:
                rr.display_table("[Client] Cache hit:")
                continue

            txid = next(tx_counter)
            qpkt = serialize_query(txid, qtype_code, qname)
            conn.send_message(qpkt, LOCAL_DNS_ADDR)

            try:
                data, _ = conn.receive_message()
            except socket.timeout:
                print("[Client] Timeout waiting for Local DNS.")
                continue

            resp = deserialize_response(data)
            if resp is None:
                print("[Client] Malformed response.")
                continue
            if resp["txid"] != txid:
                print("[Client] Mismatched transaction ID; ignoring.")
                continue

            if resp["result"] == "Record not found":
                print(f"[Client] {qname} {qtype_name}: Record not found")
                rr.display_table("[Client] RR table:")
                continue

            atype_name = DNSTypes.get_type_name(resp["atype"]) or qtype_name
            rr.add_record(resp["name"], atype_name, resp["result"], ttl=resp["ttl"], static=False)
            rr.display_table("[Client] Saved response:")

    except KeyboardInterrupt:
        print("\n[Client] Keyboard interrupt — exiting.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

