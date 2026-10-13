"""Synthetic FIT activity, never a real athlete's track. FIT SDK field units."""
import struct
from fitdecode import profile
from fitdecode.utils import compute_crc


def make_fit(indoor=False, sport=1):
    payload = bytearray()
    def define(local, global_num, names):
        fields = [next(f for f in profile.MESSAGE_TYPES[global_num].fields.values() if f.name == name) for name in names]
        payload.extend(bytes([0x40 | local, 0, 0]) + struct.pack('<H', global_num) + bytes([len(fields)]))
        for f in fields:
            base = getattr(f.type, 'base_type', None) or f.type
            payload.extend(bytes([f.def_num, base.size, base.identifier]))
        return fields
    def record(local, fields, values):
        payload.append(local)
        for f in fields:
            base = getattr(f.type, 'base_type', None) or f.type
            value = values[f.name]
            raw = round((value + (f.offset or 0)) * (f.scale or 1))
            payload.extend(struct.pack('<' + base.fmt, raw))
    stamp = 1136188800  # 2026-01-01 UTC in the FIT epoch.
    names = ['timestamp', 'distance', 'heart_rate', 'cadence', 'power', 'altitude', 'temperature',
             'step_length', 'vertical_oscillation', 'vertical_ratio', 'stance_time', 'stance_time_balance']
    if not indoor:
        names += ['position_lat', 'position_long']
    fields = define(0, 20, names)
    for i in range(61):
        record(0, fields, {'timestamp': stamp + 10 * i, 'distance': 25 * i, 'heart_rate': 140,
                          'cadence': 83, 'power': 276, 'altitude': 10 + .3 * i, 'temperature': 29,
                          'step_length': 960, 'vertical_oscillation': 84, 'vertical_ratio': 8.8,
                          'stance_time': 259, 'stance_time_balance': 50,
                          'position_lat': 0, 'position_long': i * 25 / 111195.08 * 2**31 / 180})
    fields = define(1, 19, ['timestamp', 'total_distance', 'total_timer_time', 'avg_heart_rate'])
    record(1, fields, {'timestamp': stamp + 600, 'total_distance': 1500, 'total_timer_time': 600, 'avg_heart_rate': 140})
    values = {'timestamp': stamp + 600, 'start_time': stamp, 'sport': sport, 'total_distance': 1500,
              'total_elapsed_time': 610, 'total_timer_time': 600, 'avg_heart_rate': 140, 'max_heart_rate': 140,
              'avg_cadence': 83, 'max_cadence': 83, 'avg_power': 276, 'max_power': 300,
              'total_calories': 120, 'total_training_effect': 3, 'total_anaerobic_training_effect': 0,
              'avg_step_length': 960, 'avg_vertical_oscillation': 84, 'avg_stance_time': 259, 'avg_vertical_ratio': 8.8}
    fields = define(2, 18, list(values))
    record(2, fields, values)
    header = struct.pack('<BBHI4s', 14, 0x20, 2190, len(payload), b'.FIT')
    header += struct.pack('<H', compute_crc(header))
    data = header + payload
    return data + struct.pack('<H', compute_crc(data))
