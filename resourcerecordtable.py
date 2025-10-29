from prettytable import PrettyTable

class ResourceRecordTable:
    record_number = 0

    def __init__(self):
        self.table = {}

    def add_record(self,name,record_type,result,ttl,static):
        self.table[name] = {"record_number" : self.record_number,
                            "type" : record_type,
                            "result" : result,
                            "ttl" : ttl,
                            "static" : static}

        self.record_number += 1

    def get_record(self, name):
        return self.table.get(name)

    def display_table(self):
        record_table = PrettyTable(['record_number', 'name', 'type', 'result', 'ttl', 'static'])

        for name, record in self.table.items():
            record_table.add_row([record['record_number'],
                                  name,
                                  record['type'],
                                  record['result'],
                                  record['ttl'],
                                  record['static']])

        print(record_table)