import errno
import socket
import sys
import threading
import time
import struct

# ports
LOCAL_PORT = 21000
AMAZONE_PORT = 22000

def listen():
    conn = UDPConnection(timeout=1)
    conn.bind(("127.0.0.1", LOCAL_PORT))
    rr = RRTable()
    pending_tx = {}  # client_address
    print(f"[local] Listening on 127.0.0.1:{LOCAL_PORT}")

    try:
        while True:
            # wait for query/response
            data, addr = conn.receive_message()
            if not data:
                continue

            parsed = deserialize(data)
            if parsed is None:
                continue

            txid = parsed["txid"]
            flags = parsed["flags"]  # 0 query, 1 response

            if flags == 0:
                # query from client
                qname = parsed["question_name"]
                qtype_code = parsed["question_type"]
                qtype_name = DNSTypes.get_type_name(qtype_code)
                print(f"[local] Received query for {qname} type {qtype_name} from {addr} (txid={txid})")

                # check RR table for record
                rec = rr.get_record(qname, qtype_name)
                if rec:
                    # round local - send response to client
                    ttl_val = 60 if rec["static"] else rec["ttl"]
                    resp = serialize_response(txid, qtype_code, qname, ttl_val, rec["result"])
                    conn.send_message(resp, addr)
                    print("[local] Sent response (from local RR):")
                    rr.display_table()
                    continue

                # not found locally
                if qname.endswith("csusm.edu"):
                    # authoritative but missing, respond
                    resp = serialize_response(txid, qtype_code, qname, 0, "Record not found")
                    conn.send_message(resp, addr)
                    print("[local] Authoritative for csusm.edu but record missing. Responded NOT FOUND.")
                    continue

                # forward to amazone authoritative server
                if "amazone" in qname or qname.endswith("amazone.com"):
                    conn.send_message(data, ("127.0.0.1", AMAZONE_PORT))
                    pending_tx[txid] = addr
                    print(f"[local] Forwarded query for {qname} to Amazone authoritative server (txid={txid})")
                    continue

                # not known domains, respond not found
                resp = serialize_response(txid, qtype_code, qname, 0, "Record not found")
                conn.send_message(resp, addr)
                print("[local] Not found and not in known domain. Responded NOT FOUND.")

            elif flags == 1:
                # response from authoritative server
                atype_code = parsed["answer_type"]
                aname = parsed["answer_name"]
                atype_name = DNSTypes.get_type_name(atype_code)
                ttl = parsed["ttl"]
                result = parsed["result"]
                print(f"[local] Received response for {aname} type {atype_name} (txid={txid}) result={result}")

                client_addr = pending_tx.pop(txid, None)
                if client_addr:
                    # forward binary response
                    conn.send_message(data, client_addr)
                    if result != "Record not found":
                        # save into rr_table
                        rr.add_record(aname, atype_name, result, ttl, static=False)
                        print("[local] Stored record received from authoritative:")
                        rr.display_table()
                    else:
                        print("[local] Authoritative responded NOT FOUND; forwarded to client.")
                else:
                    print("[local] Unsolicited response received (no matching pending txid). Ignoring.")

    except KeyboardInterrupt:
        print("Keyboard interrupt received, exiting...")
    finally:
        conn.close()


def main():
    local_dns_address = ("127.0.0.1", 21000)
    listen()


def serialize_query(txid: int, qtype_code: int, name: str) -> bytes:
    name_b = name.encode("utf-8")
    flags = 0
    return struct.pack("!IBB H", txid, flags, qtype_code, len(name_b)) + name_b


def serialize_response(txid: int, atype_code: int, name: str, ttl: int, result: str) -> bytes:
    name_b = name.encode("utf-8")
    res_b = result.encode("utf-8")
    flags = 1
    return struct.pack("!IBB H", txid, flags, atype_code, len(name_b)) + name_b + struct.pack("!I H", ttl, len(res_b)) + res_b


def deserialize(data: bytes):
    try:
        if len(data) < 8:
            return None
        txid, flags = struct.unpack("!IB", data[:5])
        if flags == 0:
            qtype = data[5]
            name_len = struct.unpack("!H", data[6:8])[0]
            name = data[8:8+name_len].decode("utf-8")
            return {
                "txid": txid,
                "flags": flags,
                "question_type": qtype,
                "question_name": name
            }
        elif flags == 1:
            atype = data[5]
            name_len = struct.unpack("!H", data[6:8])[0]
            name_start = 8
            name = data[name_start:name_start+name_len].decode("utf-8")
            ttl = struct.unpack("!I", data[name_start+name_len:name_start+name_len+4])[0]
            res_len = struct.unpack("!H", data[name_start+name_len+4:name_start+name_len+6])[0]
            res_start = name_start+name_len+6
            result = data[res_start:res_start+res_len].decode("utf-8")
            return {
                "txid": txid,
                "flags": flags,
                "answer_type": atype,
                "answer_name": name,
                "ttl": ttl,
                "result": result
            }
        else:
            return None
    except Exception as e:
        print(f"[deserialize] Error parsing data: {e}")
        return None


class RRTable:
    def __init__(self):
        self.records = []
        self.record_number = 0

        # start background thread to decrement
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self.__decrement_ttl, daemon=True)
        self.thread.start()

        # seed authoritative csums record
        self.add_record("www.csusm.edu", "A", "144.37.5.45", ttl=None, static=True)

    def add_record(self, name: str, type_name: str, result: str, ttl: int = 60, static: bool = False):
        with self.lock:
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
                    return r.copy()
            return None

    def display_table(self):
        with self.lock:
            print("record_no,name,type,result,ttl,static")
            for r in self.records:
                ttl = "None" if r["static"] else str(r["ttl"])
                static_flag = 1 if r["static"] else 0
                print(f'{r["record_no"]},{r["name"]},{r["type"]},{r["result"]},{ttl},{static_flag}')
            print("")

    def __decrement_ttl(self):
        while True:
            with self.lock:
                changed = False
                for r in list(self.records):
                    if not r["static"]:
                        # decrement TTL
                        r["ttl"] -= 1
                        if r["ttl"] <= 0:
                            changed = True
                if changed:
                    self.__remove_expired_records()
            time.sleep(1)

    def __remove_expired_records(self):
        new_records = [r for r in self.records if not (not r["static"] and r["ttl"] <= 0)]
        for i, r in enumerate(new_records):
            r["record_no"] = i
        self.records = new_records
        self.record_number = len(self.records)


class DNSTypes:
    name_to_code = {
        "A": 0b1000,
        "AAAA": 0b0100,
        "CNAME": 0b0010,
        "NS": 0b0001,
    }

    code_to_name = {code: name for name, code in name_to_code.items()}

    @staticmethod
    def get_type_code(type_name: str):
        return DNSTypes.name_to_code.get(type_name, None)

    @staticmethod
    def get_type_name(type_code: int):
        return DNSTypes.code_to_name.get(type_code, None)


class UDPConnection:
    def __init__(self, timeout: int = 1):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(timeout)
        self.is_bound = False

    def send_message(self, message, address: tuple):
        if isinstance(message, str):
            data = message.encode()
        else:
            data = message
        self.socket.sendto(data, address)

    def receive_message(self):
        while True:
            try:
                data, address = self.socket.recvfrom(4096)
                return data, address
            except socket.timeout:
                continue
            except OSError as e:
                if e.errno == errno.ECONNRESET:
                    print("Error: Unable to reach the other socket. It might not be up and running.")
                else:
                    print(f"Socket error: {e}")
                self.close()
                sys.exit(1)
            except KeyboardInterrupt:
                raise

    def bind(self, address: tuple):
        if self.is_bound:
            print(f"Socket is already bound to address: {self.socket.getsockname()}")
            return
        self.socket.bind(address)
        self.is_bound = True

    def close(self):
        self.socket.close()


if __name__ == "__main__":
    main()
