"""Pure, versioned deterministic engine. Does not produce medical advice or GPS output."""
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from lxml import etree as ET

VERSION = "1.1.0"
MAX_POINTS = 100_000


class GPXError(ValueError):
    pass


@dataclass
class Point:
    lat: float | None
    lon: float | None
    time: datetime | None
    ele: float | None
    hr: float | None
    metrics: dict = field(default_factory=dict)
    distance_m: float | None = None


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_gpx(data: bytes):
    if len(data) > 10 * 1024 * 1024:
        raise GPXError("GPX 파일은 10 MiB 이하여야 합니다.")
    try:
        parser = ET.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False,
                              remove_comments=True, remove_pis=True)
        root = ET.fromstring(data, parser)
        if root.getroottree().docinfo.doctype:
            raise GPXError("DTD/엔티티 선언은 허용하지 않습니다.")
    except Exception as exc:
        raise GPXError("안전한 GPX XML 파일을 읽을 수 없습니다.") from exc
    if local(root.tag) != "gpx":
        raise GPXError("GPX 루트가 필요합니다.")
    segments, warnings, count = [], set(), 0
    for segment in root.iter():
        if local(segment.tag) != "trkseg":
            continue
        points = []
        for node in segment:
            if local(node.tag) != "trkpt":
                continue
            count += 1
            if count > MAX_POINTS:
                raise GPXError("트랙 포인트는 100,000개 이하여야 합니다.")
            lat, lon = number(node.get("lat")), number(node.get("lon"))
            if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise GPXError("위도 또는 경도 범위가 유효하지 않습니다.")
            values = {local(x.tag): x.text for x in node.iter()}
            stamp = None
            try:
                stamp = datetime.fromisoformat((values.get("time") or "").strip().replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    raise ValueError("timezone missing")
                stamp = stamp.astimezone(timezone.utc)
            except ValueError:
                stamp = None
                warnings.add("시간이 누락되거나 유효하지 않아 페이스가 제한됩니다.")
            hr = number(values.get("hr"))
            if hr is not None and not 30 <= hr <= 240:
                hr = None
                warnings.add("범위 밖 심박 측정치를 제외했습니다.")
            elevation = number(values.get("ele"))
            if elevation is not None and not -500 <= elevation <= 10000:
                elevation = None
                warnings.add("범위 밖 고도 측정치를 제외했습니다.")
            from .activity_metrics import gpx_metrics
            points.append(Point(lat, lon, stamp, elevation, hr, gpx_metrics(values, warnings)))
        if points:
            segments.append(points)
    if sum(len(s) for s in segments) < 2 or not any(len(s) > 1 for s in segments):
        raise GPXError("연속된 트랙 포인트가 2개 이상 필요합니다.")
    return segments, warnings


def haversine(a, b):
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b.lon - a.lon) / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, h)))


def analyze(data: bytes):
    segments, warnings = parse_gpx(data)
    return analyze_points(segments, warnings)


def analyze_points(segments, warnings):
    distance = moving = ascent = descent = hr_sum = hr_seconds = tracked_seconds = 0.0
    timing_complete = all(p.time is not None for s in segments for p in s)
    edges, series = [], []
    hr_histogram = {}
    all_times = [p.time for s in segments for p in s if p.time]
    prev_segment_end = None
    for segment in segments:
        if series:
            series.append({"distance_km": round(distance / 1000, 3), "elevation_m": None,
                           "heart_rate_bpm": None, "segment_break": True})
        elevation_anchor = segment[0].ele
        if prev_segment_end and segment[0].time and segment[0].time < prev_segment_end:
            timing_complete = False
            warnings.add("트랙 구간의 시간이 역순입니다.")
        prev_segment_end = segment[-1].time
        for a, b in zip(segment, segment[1:]):
            if a.distance_m is not None and b.distance_m is not None:
                meters = b.distance_m - a.distance_m
                if meters < 0:
                    warnings.add("기기 누적 거리가 역순인 연결을 제외했습니다.")
                    continue
            elif a.lat is not None and b.lat is not None:
                meters = haversine(a, b)
            else:
                warnings.add("GPS와 기기 거리 모두 없는 구간은 거리 계산에서 제외했습니다.")
                continue
            dt = (b.time - a.time).total_seconds() if a.time and b.time else None
            if dt is None or dt <= 0:
                timing_complete = False
                warnings.add("누락 또는 역순/중복 시간으로 페이스를 계산하지 않습니다.")
            if (dt and dt > 0 and meters / dt > 12) or ((dt is None or dt <= 0) and meters > 2000):
                warnings.add("비현실적인 GPS 급변 연결을 제외했습니다.")
                elevation_anchor = b.ele
                continue
            if dt and dt > 0:
                tracked_seconds += dt
                if a.hr is not None and b.hr is not None:
                    hr_sum += (a.hr + b.hr) / 2 * dt
                    hr_seconds += dt
                    for hr in (a.hr, b.hr):
                        key = str(int(round(hr)))
                        hr_histogram[key] = hr_histogram.get(key, 0) + dt / 2
            move_dt = dt if dt and dt > 0 and meters / dt >= 0.5 else 0.0
            distance += meters
            moving += move_dt
            edges.append((meters, move_dt))
            if b.ele is not None and elevation_anchor is not None:
                change = b.ele - elevation_anchor
                if abs(change) >= 3:
                    ascent += max(0, change)
                    descent += max(0, -change)
                    elevation_anchor = b.ele
            else:
                elevation_anchor = b.ele
            series.append({"distance_km": round(distance / 1000, 3), "elevation_m": b.ele,
                           "heart_rate_bpm": b.hr, **b.metrics,
                           "elapsed_seconds": round((b.time - all_times[0]).total_seconds(), 1) if b.time and all_times else None,
                           "sample_seconds": dt if dt and dt > 0 else None,
                           "speed_kmh": round(meters / dt * 3.6, 3) if dt and dt > 0 else None,
                           "pace_sec_km": round(dt / meters * 1000, 1) if move_dt and meters else None})
    if distance == 0:
        warnings.add("유효한 이동 거리가 없습니다.")
    all_points = [p for s in segments for p in s]
    if any(p.ele is None for p in all_points):
        warnings.add("고도 결측이 있어 상승/하강량은 불완전합니다.")
    if hr_seconds == 0:
        warnings.add("시간 가중 심박을 계산할 데이터가 없습니다.")
    if len(segments) > 1:
        warnings.add("분리된 트랙 구간 사이의 거리는 합산하지 않았습니다.")
    splits, split_dist, split_seconds = [], 0.0, 0.0
    for meters, secs in edges:
        while meters > 1e-7:
            portion = min(meters, 1000 - split_dist)
            used_seconds = secs * portion / meters
            split_dist += portion
            split_seconds += used_seconds
            meters -= portion
            secs -= used_seconds
            if split_dist >= 1000 - 1e-6:
                splits.append({"index": len(splits) + 1, "distance_km": 1.0, "partial": False,
                               "pace_sec_km": round(split_seconds, 1) if timing_complete and split_seconds else None})
                split_dist = split_seconds = 0.0
    if split_dist > 1e-5:
        splits.append({"index": len(splits) + 1, "distance_km": round(split_dist / 1000, 3), "partial": True,
                       "pace_sec_km": round(split_seconds / (split_dist / 1000), 1) if timing_complete and split_seconds else None})
    stride = max(1, math.ceil(len(series) / 500))
    from .activity_metrics import summarize
    extra = summarize(series, all_points, timing_complete)
    return {"engine_version": VERSION, "started_at": all_times[0].isoformat() if all_times else None,
            "distance_km": round(distance / 1000, 3),
            "elapsed_seconds": round((max(all_times) - min(all_times)).total_seconds(), 1) if timing_complete and all_times else None,
            "moving_seconds": round(moving, 1) if timing_complete else None,
            "pace_sec_km": round(moving / (distance / 1000), 1) if timing_complete and distance and moving else None,
            "avg_heart_rate": round(hr_sum / hr_seconds, 1) if hr_seconds else None,
            "heart_rate_coverage": round(hr_seconds / tracked_seconds, 3) if tracked_seconds else 0,
            "ascent_m": round(ascent, 1) if any(p.ele is not None for p in all_points) else None,
            "descent_m": round(descent, 1) if any(p.ele is not None for p in all_points) else None,
            "point_count": len(all_points), "timing_complete": timing_complete,
            **extra, "heart_rate_seconds": hr_histogram, "splits": splits, "series": [p for i, p in enumerate(series) if i % stride == 0 or p.get("segment_break") or i == len(series)-1], "warnings": sorted(warnings)}
