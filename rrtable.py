class Rrtable:
    dict = None
    int = None
    str = None
    type = None
    result = None
    ttl = None
    static = None

    def __init__(self):
        self.table = {}

    def add_record(self, record_number,name,type,result,ttl,static):
        self.table[record_number] = {"name" : name,
                                     "type" : type,
                                     "result" : result,
                                     "ttl" : ttl,
                                     "static" : static}

    def get_record(self, record_number):
        return self.table.get(self, record_number)