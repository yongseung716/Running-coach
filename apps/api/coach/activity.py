"""Bounded GPX/FIT import; original vendor values remain separate from calculations."""
import io
import zipfile
from datetime import datetime, timezone

import fitdecode

from .analysis import GPXError, MAX_POINTS, Point, analyze_points, number, parse_gpx
from .activity_metrics import valid

MAX_BYTES = 10 * 1024 * 1024
FIT_METRICS = {
    "cadence": ("cadence_spm", 2), "power": ("power_w", 1),
    "step_length": ("stride_length_m", .001),
    "vertical_oscillation": ("vertical_oscillation_cm", .1),
    "vertical_ratio": ("vertical_ratio_pct", 1), "stance_time": ("ground_contact_ms", 1),
    "stance_time_balance": ("ground_contact_balance_pct", 1),
    "temperature": ("temperature_c", 1), "performance_condition": ("performance_condition", 1),
}
SUMMARY_FIELDS = {
    "total_distance": ("distance_km", .001), "total_elapsed_time": ("elapsed_seconds", 1),
    "total_timer_time": ("timer_seconds", 1), "total_calories": ("calories_kcal", 1),
    "avg_heart_rate": ("avg_heart_rate", 1), "max_heart_rate": ("max_heart_rate", 1),
    "avg_cadence": ("avg_cadence_spm", 2), "max_cadence": ("max_cadence_spm", 2),
    "avg_power": ("avg_power_w", 1), "max_power": ("max_power_w", 1),
    "normalized_power": ("normalized_power_w", 1),
    "total_training_effect": ("aerobic_training_effect", 1),
    "total_anaerobic_training_effect": ("anaerobic_training_effect", 1),
    "training_load_peak": ("training_load", 1),
    "avg_vertical_oscillation": ("avg_vertical_oscillation_cm", .1),
    "avg_stance_time": ("avg_ground_contact_ms", 1),
    "avg_stance_time_balance": ("avg_ground_contact_balance_pct", 1),
    "avg_step_length": ("avg_stride_length_m", .001),
    "avg_vertical_ratio": ("avg_vertical_ratio_pct", 1),
    "total_ascent": ("ascent_m", 1), "total_descent": ("descent_m", 1),
    "avg_temperature": ("avg_temperature_c", 1), "min_temperature": ("min_temperature_c", 1),
    "max_temperature": ("max_temperature_c", 1),
}


def prepare_upload(data, filename):
    if len(data) > MAX_BYTES:
        raise GPXError("파일은 10 MiB 이하여야 합니다.")
    extension = (filename or '').rsplit('.', 1)[-1].lower()
    if extension == 'zip':
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                files = [f for f in archive.infolist() if not f.is_dir()]
                if len(files) != 1 or not files[0].filename.lower().endswith('.fit'):
                    raise GPXError("ZIP에는 FIT 파일 하나만 포함되어야 합니다.")
                info = files[0]
                if info.file_size > MAX_BYTES or info.flag_bits & 1 or info.file_size > max(1, info.compress_size) * 200:
                    raise GPXError("압축 파일 크기·암호화·압축률 제한을 초과했습니다.")
                data = archive.read(info)
        except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
            raise GPXError("안전한 FIT 압축 파일을 읽을 수 없습니다.") from exc
        extension = 'fit'
    if extension not in {'gpx', 'fit'}:
        raise GPXError("GPX, FIT 또는 FIT 하나가 든 ZIP 파일을 선택하세요.")
    parse_activity(data, extension)
    return data, extension


def parse_fit(data):
    if len(data) > MAX_BYTES:
        raise GPXError("FIT 파일은 10 MiB 이하여야 합니다.")
    if len(data) < 14 or data[8:12] != b'.FIT':
        raise GPXError("FIT 파일 서명이 올바르지 않습니다.")
    records, summaries, laps, warnings = [], [], [], set()
    segments, current = [], []
    messages = 0
    try:
        with fitdecode.FitReader(io.BytesIO(data), check_crc=fitdecode.CrcCheck.RAISE,
                                 error_handling=fitdecode.ErrorHandling.RAISE) as reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                messages += 1
                if messages > MAX_POINTS * 3:
                    raise GPXError("FIT 메시지가 너무 많습니다.")
                values = {f.name: f.value for f in frame.fields}
                if frame.name == 'session':
                    summaries.append(values)
                elif frame.name == 'lap':
                    laps.append(values)
                elif frame.name == 'event' and values.get('event') == 'timer' and str(values.get('event_type', '')).startswith('stop'):
                    if current:
                        segments.append(current); current = []
                elif frame.name == 'record':
                    records.append(values); current.append(values)
                    if len(records) > MAX_POINTS:
                        raise GPXError("트랙 포인트는 100,000개 이하여야 합니다.")
    except GPXError:
        raise
    except Exception as exc:
        raise GPXError("FIT CRC 또는 데이터 형식 검증에 실패했습니다.") from exc
    if current:
        segments.append(current)
    if len(summaries) > 1:
        raise GPXError("멀티스포츠 FIT는 러닝 활동 하나씩 내보내세요.")
    summary = summaries[0] if summaries else {}
    if summary.get('sport') not in {None, 'running', 'walking'}:
        raise GPXError("현재 러닝·걷기 FIT 활동만 지원합니다.")
    parsed = []
    for group in segments:
        points = []
        for v in group:
            lat, lon = number(v.get('position_lat')), number(v.get('position_long'))
            if lat is not None and lon is not None:
                lat, lon = lat * 180 / 2**31, lon * 180 / 2**31
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    lat = lon = None; warnings.add("범위 밖 FIT GPS 좌표를 제외했습니다.")
            else:
                lat = lon = None
            stamp = v.get('timestamp')
            if isinstance(stamp, datetime):
                stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
            else:
                stamp = None; warnings.add("FIT 시간이 없어 페이스 계산이 제한됩니다.")
            hr = number(v.get('heart_rate'))
            hr = hr if hr is not None and 30 <= hr <= 240 else None
            ele = number(v.get('enhanced_altitude'))
            if ele is None:
                ele = number(v.get('altitude'))
            ele = ele if ele is not None and -500 <= ele <= 10000 else None
            metrics = {}
            for field, (key, scale) in FIT_METRICS.items():
                value = number(v.get(field))
                if field == 'cadence' and value is not None:
                    value += number(v.get('fractional_cadence')) or 0
                metrics[key] = valid(value * scale, key) if value is not None else None
            distance = number(v.get('distance'))
            distance = distance if distance is not None and 0 <= distance <= 2_000_000 else None
            points.append(Point(lat, lon, stamp, ele, hr, metrics, distance))
        if points:
            parsed.append(points)
    if not any(len(s) >= 2 for s in parsed):
        raise GPXError("FIT에는 연속된 기록 표본이 2개 이상 필요합니다.")
    device = {}
    for field, (key, scale) in SUMMARY_FIELDS.items():
        value = number(summary.get(field))
        if value is not None:
            value *= scale
            if key.endswith('temperature_c') or value >= 0:
                device[key] = round(value, 3)
    for field, key in [('enhanced_avg_speed', 'avg_speed_kmh'), ('enhanced_max_speed', 'max_speed_kmh')]:
        value = number(summary.get(field))
        if value is None:
            value = number(summary.get('avg_speed' if 'avg_' in field else 'max_speed'))
        if value is not None and 0 <= value <= 12:
            device[key] = round(value * 3.6, 3)
    if device.get('avg_speed_kmh'):
        device['avg_pace_sec_km'] = round(3600 / device['avg_speed_kmh'], 1)
    if device.get('max_speed_kmh'):
        device['best_pace_sec_km'] = round(3600 / device['max_speed_kmh'], 1)
    for key in ['aerobic_training_effect', 'anaerobic_training_effect']:
        if device.get(key, 0) > 5:
            device.pop(key, None)
    lap_output = []
    for i, v in enumerate(laps[:500]):
        dist, timer = number(v.get('total_distance')), number(v.get('total_timer_time'))
        lap_output.append({'index': i + 1, 'distance_km': round(dist / 1000, 3) if dist is not None and dist >= 0 else None,
                           'duration_seconds': timer if timer is not None and timer >= 0 else None,
                           'pace_sec_km': round(timer / dist * 1000, 1) if dist and dist > 0 and timer and timer > 0 else None,
                           'avg_heart_rate': number(v.get('avg_heart_rate')), 'source': 'device'})
    return parsed, warnings, device, lap_output


def parse_activity(data, file_format):
    if file_format == 'gpx':
        segments, warnings = parse_gpx(data)
        return segments, warnings, {}, []
    if file_format == 'fit':
        return parse_fit(data)
    raise GPXError("지원하지 않는 파일 형식입니다.")


def analyze_activity(data, file_format='gpx'):
    segments, warnings, device, laps = parse_activity(data, file_format)
    result = analyze_points(segments, warnings)
    result.update(file_format=file_format, device_summary=device, laps=laps,
                  sources={'calculated': 'PACE engine 1.1.0', 'device_summary': 'FIT 원본' if device else '데이터 없음'},
                  unavailable_vendor_metrics=['경사 조정 페이스', '바디 배터리', '예상 수분 손실', '섭취 수분', '기본 운동 효과 분류'])
    for key, metric in result['metrics'].items():
        fallback = device.get('avg_' + key)
        if metric['avg'] is None and fallback is not None and valid(fallback, key) is not None:
            metric.update(avg=fallback, source='device_summary')
    return result


def private_route(data, file_format):
    segments, _, _, _ = parse_activity(data, file_format)
    routes = []
    for segment in segments:
        gps = [p for p in segment if p.lat is not None and p.lon is not None]
        stride = max(1, (len(gps) + 999) // 1000)
        routes.append([{'lat': p.lat, 'lon': p.lon} for i, p in enumerate(gps) if i % stride == 0 or i == len(gps) - 1])
    return {'segments': routes, 'privacy': 'owner_only_no_external_map_tiles'}
