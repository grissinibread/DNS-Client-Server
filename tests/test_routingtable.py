import pytest

from resourcerecordtable import ResourceRecordTable

@pytest.fixture
def routing_table():
    return ResourceRecordTable()

def test_initialization(routing_table):
    assert routing_table.table == {}

def test_add_and_get_record(routing_table):
    routing_table.add_record("example.com" , "A", "", 300, True)
    record = routing_table.get_record("example.com")

    assert record == {"record_number": 0, "type": "A", "result": "", "ttl": 300, "static": True}

def test_get_nonexistent_record(routing_table):
    record = routing_table.get_record("")
    assert record is None

def test_display_table(capsys, routing_table):
    routing_table.add_record("example.com", "A", "", 300, True)
    routing_table.add_record("example.org", "AAAA", "", 200, False)

    routing_table.display_table()

    captured = capsys.readouterr()
    assert "record_number" in captured.out
    assert "example.com" in captured.out
    assert "example.org" in captured.out