from prettytable import PrettyTable

class RoutingTable:
    def __init__(self):
        self.table = {}

    def add_record(self, record_number,name,type,result,ttl,static):
        self.table[record_number] = {"name" : name,
                                     "type" : type,
                                     "result" : result,
                                     "ttl" : ttl,
                                     "static" : static}

    def get_record(self, record_number):
        return self.table.get(record_number)

    def display_table(self):
        record_table = PrettyTable(['record_number', 'name', 'type', 'result', 'ttl', 'static'])

        for recordNumber, record in self.table.items():
            record_table.add_row([recordNumber,
                                  record['name'],
                                  record['type'],
                                  record['result'],
                                  record['ttl'],
                                  record['static']])

        print(record_table)