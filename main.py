import pymem
import json
import sys
from construct import Struct, Int64ul
import psutil


entry_struct = Struct(
    "string_o" / Int64ul,
    "id_o" / Int64ul
)

def find_process_by_name(name):
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'].lower() == name.lower():
            return proc
    return None

def read_null(pm, addr):
    ret = bytearray()
    while True:
        byte = pm.read_bytes(addr, 1)
        if byte == b"\x00":
            break
        ret.extend(byte)
        addr += 1
    return ret.decode(errors="ignore")

def export(pm, start_address, count):
    ret = {}
    start = start_address
    for i in range(count):
        try:
            data = pm.read_bytes(start, 16)
            entry = entry_struct.parse(data)
            start += 16
            string = read_null(pm, entry.string_o)
            id_o = read_null(pm, entry.id_o)
            ret[id_o] = string
        except Exception as e:
            print(f"Error at index {i}: {e}")
            start += 16
            continue
    with open("localize.json", "w", encoding="utf8") as f:
        json.dump(ret, f, indent=4, ensure_ascii=False)

def _import(pm, start_address, count):
    strings = json.load(open("localize.json", encoding="utf8"))
    to_write = bytearray()
    table_offsets = {}

    for id, string in strings.items():
        table_offsets[id] = len(to_write)
        to_write.extend(string.encode() + b"\x00")

    new_table = pm.allocate(len(to_write) * 2)
    if not new_table:
        raise MemoryError("Failed to allocate memory in the target process.")
    
    pm.write_bytes(new_table, bytes(to_write), len(to_write))

    start = start_address
    for i in range(count):
        try:
            data = pm.read_bytes(start, 16)
            entry = entry_struct.parse(data)
            start += 16
            id = read_null(pm, entry.id_o)
            if id in strings:
                print(f"Hooking {id} to {hex(table_offsets[id] + new_table)} from {hex(entry.string_o)}. New string: {strings[id]}")
                new_entry = dict(string_o=table_offsets[id] + new_table, id_o=entry.id_o)
                pm.write_bytes(start - 16, entry_struct.build(new_entry), entry_struct.sizeof())
        except Exception as e:
            print(f"Error at index {i}: {e}")
            start += 16
            continue

def main():
    proc = find_process_by_name("iw7_ship.exe")
    if not proc:
        print("Could not find process: iw7_ship.exe")
        sys.exit(1)

    pm = pymem.Pymem(proc.info['pid'])
    start_address = pm.base_address + 0x35135B0  
    end_address = Int64ul.parse(pm.read_bytes(start_address, 8))  
    start_address += 8
    count = (end_address - start_address) // 16

    if len(sys.argv) == 1:
        print("""Usage:
    -e: Create localize.json file
    -i: Import localize.json to game""")
        sys.exit(1)

    if sys.argv[1] == "-e":
        export(pm, start_address, count)
    elif sys.argv[1] == "-i":
        _import(pm, start_address, count)
    else:
        print(f"Unknown option {sys.argv[1]}")
        sys.exit(1)

if __name__ == "__main__":
    main()
