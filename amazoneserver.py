import errno
import socket
import sys

from resourcerecordtable import ResourceRecordTable

def listen(table, udp_connection):
    try:
        while True:
            # Wait for query
            message, address = udp_connection.receive_message()
            split_message = message.split()
            deserialized_message = deserialize(split_message)

            # Check RR table for record
            # If not found, add "Record not found" in the DNS response
            #TODO: fix the format of the DNS query
            record = table.get_record(deserialized_message["name"])
            if record is not None:
                response = serialize(split_message,
                                     deserialized_message["transaction_id"],
                                     deserialized_message["flag"],
                                     deserialized_message["question_name"],
                                     deserialized_message["question_type"],
                                     record["name"],
                                     record["type"],
                                     record["result"])
            else:
                response = "Record not found" # I'm sure this is not the correct format

            # Else, return record in DNS response
            # The format of the DNS query and response is in the project description
            udp_connection.send_message(response, address)

            # Display RR table
            table.display_table()

    except KeyboardInterrupt:
        print("Keyboard interrupt received, exiting...")
    finally:
        # Close UDP socket
        udp_connection.close()


def main():
    table = RRTable()
    # Add initial records
    # These can be found in the test cases diagram
    table.add_record("shop.amazone.com", "A", "3.33.147.88", "None", 1)
    table.add_record("cloud.amazone.com", "A", "3.33.147.88", "None", 0)

    amazone_dns_address = ("127.0.0.1", 22000)
    # Bind address to UDP socket
    udp_connection = UDPConnection()
    udp_connection.bind(amazone_dns_address)

    listen(table, udp_connection)

def serialize(split_message,
              flag,
              question_name,
              question_type,
              answer_name,
              answer_type,
              answer_result,
              ttl):

    return f"{split_message[0]} {flag} {question_name} {question_type} {answer_name} {answer_type} {answer_result} {ttl}"


# deserialize function to extract the name from the message
def deserialize(split_message):
    return {"transaction_id" : split_message[0],
            "flag" : split_message[1],
            "question_name" : split_message[2],
            "question_type" : split_message[3],
            "answer_name" : split_message[4],
            "answer_type" : split_message[5],
            "answer_ttl" : split_message[6],
            "answer_result" : split_message[7]}


class RRTable:
    def __init__(self):
        self.records = ResourceRecordTable()

    def add_record(self, name, record_type, result, ttl, static):
        self.records.add_record(name, record_type, result, ttl, static)

    def get_record(self, record_number):
        return self.records.get_record( record_number)

    def display_table(self):
        # Display the table in the following format (include the column names):
        # record_number,name,type,result,ttl,static
        self.records.display_table()


class DNSTypes:
    """
    A class to manage DNS query types and their corresponding codes.

    Examples:
    >>> DNSTypes.get_type_code('A')
    8
    >>> DNSTypes.get_type_name(0b0100)
    'AAAA'
    """

    name_to_code = {
        "A": 0b1000,
        "AAAA": 0b0100,
        "CNAME": 0b0010,
        "NS": 0b0001,
    }

    code_to_name = {code: name for name, code in name_to_code.items()}

    @staticmethod
    def get_type_code(type_name: str):
        """Gets the code for the given DNS query type name, or None"""
        return DNSTypes.name_to_code.get(type_name, None)

    @staticmethod
    def get_type_name(type_code: int):
        """Gets the DNS query type name for the given code, or None"""
        return DNSTypes.code_to_name.get(type_code, None)


class UDPConnection:
    """A class to handle UDP socket communication, capable of acting as both a client and a server."""

    def __init__(self, timeout: int = 1):
        """Initializes the UDPConnection instance with a timeout. Defaults to 1."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(timeout)
        self.is_bound = False

    def send_message(self, message: str, address: tuple[str, int]):
        """Sends a message to the specified address."""
        self.socket.sendto(message.encode(), address)

    def receive_message(self):
        """
        Receives a message from the socket.

        Returns:
            tuple (data, address): The received message and the address it came from.

        Raises:
            KeyboardInterrupt: If the program is interrupted manually.
        """
        while True:
            try:
                data, address = self.socket.recvfrom(4096)
                return data.decode(), address
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

    def bind(self, address: tuple[str, int]):
        """Binds the socket to the given address. This means it will be a server."""
        if self.is_bound:
            print(f"Socket is already bound to address: {self.socket.getsockname()}")
            return
        self.socket.bind(address)
        self.is_bound = True

    def close(self):
        """Closes the UDP socket."""
        self.socket.close()


if __name__ == "__main__":
    main()
