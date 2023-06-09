import struct
import logging
from e6xdb.date_time_utils import FORMATS, floor_div, floor_mod
from datetime import datetime, timedelta
from e6xdb.constants import ZONE

_logger = logging.getLogger(__name__)


class DataInputStream:
    def __init__(self, stream):
        self.stream = stream

    def read_boolean(self):
        return struct.unpack('?', self.stream.read(1))[0]

    def read_bytes(self, byte_array):
        for i in range(len(byte_array)):
            byte_array[i] = struct.unpack('B', self.stream.read(1))[0]
        return byte_array

    def read_int_96(self):
        return struct.unpack('B', self.stream.read(12))[0]

    def read_byte(self):
        return struct.unpack('b', self.stream.read(1))[0]

    def read_unsigned_byte(self):
        return struct.unpack('B', self.stream.read(1))[0]

    def read_char(self):
        return chr(struct.unpack('>H', self.stream.read(2))[0])

    def read_double(self):
        return struct.unpack('>d', self.stream.read(8))[0]

    def read_float(self):
        return struct.unpack('>f', self.stream.read(4))[0]

    def read_short(self):
        return struct.unpack('>h', self.stream.read(2))[0]

    def read_unsigned_short(self):
        return struct.unpack('>H', self.stream.read(2))[0]

    def read_long(self):
        return struct.unpack('>q', self.stream.read(8))[0]

    def read_utf(self):
        utf_length = struct.unpack('>H', self.stream.read(2))[0]
        return self.stream.read(utf_length)

    def read_int(self):
        return struct.unpack('>i', self.stream.read(4))[0]

    def read_unsigned_int(self):
        return struct.unpack('>I', self.stream.read(4))[0]


class FieldInfo:
    def __init__(self, name, field_type, date_format, zone):
        self.name = name
        self.field_type = field_type
        self.date_format = date_format
        self.zone = zone

    def get_zone(self):
        if self.field_type == 'DATE' or self.field_type == 'DATETIME':
            return self.zone
        return None

    def get_format(self):
        if self.field_type == 'DATE' or self.field_type == 'DATETIME':
            return self.date_format
        return None

    def get_field_type(self):
        return self.field_type

    def get_name(self):
        return self.name


def get_query_columns_info(buffer):
    result_meta_bytes = DataInputStream(buffer)
    rowcount = result_meta_bytes.read_long()
    field_count = result_meta_bytes.read_int()
    columns_description = list()

    for i in range(field_count):
        name = result_meta_bytes.read_utf().decode()
        field_type = result_meta_bytes.read_utf().decode()
        zone = result_meta_bytes.read_utf().decode()
        date_format = result_meta_bytes.read_utf().decode()
        field_info = FieldInfo(name, field_type, date_format, zone)
        columns_description.append(field_info)
    return rowcount, columns_description


def read_values_from_array(query_columns_description: list, dis: DataInputStream) -> list:
    value_array = list()
    for i in query_columns_description:
        dtype = i.get_field_type()
        isPresent = dis.read_byte()
        date_format = i.get_format()
        if isPresent == 0:
            value_array.append(None)
            continue
        try:
            if dtype == "LONG":
                value_array.append(dis.read_long())
            elif dtype == "DATE":
                epoch_seconds = floor_div(dis.read_long(), 1000_000)
                date = datetime.fromtimestamp(epoch_seconds, ZONE)
                value_array.append(date.strftime("%Y-%m-%d"))
            elif dtype == "DATETIME":
                epoch_micros = dis.read_long()
                epoch_seconds = floor_div(epoch_micros, 1000_000)
                micros_of_the_day = floor_mod(epoch_micros, 1000_000)
                date_time = datetime.fromtimestamp(epoch_seconds, ZONE)
                date_time = date_time + timedelta(microseconds=micros_of_the_day)
                value_array.append(date_time.strftime("%Y-%m-%d %H:%M:%S"))
            elif dtype == "STRING" or dtype == "ARRAY" or dtype == "MAP" or dtype == "STRUCT":
                value_array.append(dis.read_utf().decode())
            elif dtype == "INT":
                value_array.append(dis.read_int())
            elif dtype == "DOUBLE":
                value_array.append(dis.read_double())
            elif dtype == "BINARY":
                value_array.append(dis.read_utf())
            elif dtype == "FLOAT":
                value_array.append(dis.read_float())
            elif dtype == "CHAR":
                value_array.append(dis.read_char())
            elif dtype == "BOOLEAN":
                value_array.append(dis.read_boolean())
            elif dtype == "SHORT":
                value_array.append(dis.read_short())
            elif dtype == "BYTE":
                value_array.append(dis.read_byte())
            elif dtype == "INT96":
                julian_day = dis.read_int()
                time = dis.read_long()
                date_time = datetime.fromtimestamp((julian_day - 2440588) * 86400)
                date_time_with_nanos = date_time + timedelta(microseconds=(time / 1000))
                value_array.append(date_time_with_nanos)
            elif dtype == "INTEGER":
                value_array.append(dis.read_int())
        except Exception as e:
            _logger.error(e)
            value_array.append('Failed to parse.')

    return value_array


def read_rows_from_batch(query_columns_description: list, dis: DataInputStream):
    is_row_present = dis.read_byte()
    if not is_row_present:
        return None
    rows = list()
    while is_row_present == 1:
        if is_row_present:
            row = read_values_from_array(query_columns_description, dis)
            rows.append(row)
            #   if rows become 1000, break it
            # if len(rows) == 1000:
            #     _logger.info("Read Batch - Breaking the loop after 1000 records")
            #     break
        is_row_present = dis.read_byte()
    return rows
