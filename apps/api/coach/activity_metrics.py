"""Measured signals and transparent calculations. No guessed vendor metrics."""
import math

BOUNDS = {
    "cadence_spm": (30, 260), "power_w": (0, 2500), "stride_length_m": (.1, 3),
    "vertical_oscillation_cm": (0, 30), "vertical_ratio_pct": (0, 30),
    "ground_contact_ms": (50, 1500), "ground_contact_balance_pct": (0, 100),
    "temperature_c": (-50, 65), "performance_condition": (-30, 30),
}
LABELS = {
    "cadence_spm": ("케이던스", "spm"), "power_w": ("파워", "W"),
    "stride_length_m": ("보폭", "m"), "vertical_oscillation_cm": ("수직 진동", "cm"),
    "vertical_ratio_pct": ("수직 비율", "%"), "ground_contact_ms": ("지면 접촉 시간", "ms"),
    "ground_contact_balance_pct": ("좌측 지면 접촉 비율", "%"),
    "temperature_c": ("센서 온도", "°C"), "performance_condition": ("운동 성과", "점"),
}


def valid(value, key):
    try:
        value = float(value)
        low, high = BOUNDS[key]
        return value if math.isfinite(value) and low <= value <= high else None
    except (ValueError, TypeError):
        return None


def gpx_metrics(values, warnings):
    mapping = {
        "cad": ("cadence_spm", 1), "cadence": ("cadence_spm", 1),
        "power": ("power_w", 1), "watts": ("power_w", 1),
        "atemp": ("temperature_c", 1), "temperature": ("temperature_c", 1),
        "stride_length": ("stride_length_m", 1), "step_length": ("stride_length_m", .001),
        "vertical_oscillation": ("vertical_oscillation_cm", .1),
        "vertical_ratio": ("vertical_ratio_pct", 1), "stance_time": ("ground_contact_ms", 1),
        "ground_contact_time": ("ground_contact_ms", 1),
        "performance_condition": ("performance_condition", 1),
    }
    result = {}
    for tag, (key, scale) in mapping.items():
        if values.get(tag) is None:
            continue
        try:
            value = float(values[tag]) * scale
        except (ValueError, TypeError):
            value = None
        # Garmin GPX cad may represent strides/min; normalization is disclosed.
        if tag == "cad" and value is not None and 30 <= value <= 125:
            value *= 2
            warnings.add("GPX cad를 보행 주기/분으로 해석하여 케이던스를 2배 환산했습니다.")
        result[key] = valid(value, key)
        if result[key] is None:
            warnings.add(f"범위 밖 {LABELS[key][0]} 측정치를 제외했습니다.")
    return result


def summarize(series, points, timing_complete):
    metrics = {}
    for key, (label, unit) in LABELS.items():
        values = [p.metrics[key] for p in points if p.metrics.get(key) is not None]
        timed = [(p.get(key), p.get("sample_seconds")) for p in series]
        weighted = [(v, dt) for v, dt in timed if v is not None and dt and dt > 0]
        avg = sum(v * dt for v, dt in weighted) / sum(dt for _, dt in weighted) if weighted else None
        metrics[key] = {"label": label, "unit": unit, "avg": round(avg, 3) if avg is not None else None,
                        "min": min(values) if values else None, "max": max(values) if values else None,
                        "source": "measured" if values else "unavailable",
                        "coverage": round(len(values) / len(points), 3) if points else 0}
    hr = [p.hr for p in points if p.hr is not None]
    elevations = [p.ele for p in points if p.ele is not None]
    paced = [(p["pace_sec_km"], p["sample_seconds"]) for p in series if p.get("pace_sec_km") and p.get("sample_seconds")]
    total = sum(dt for _, dt in paced)
    mean = sum(v * dt for v, dt in paced) / total if total else None
    cv = math.sqrt(sum(dt * (v - mean) ** 2 for v, dt in paced) / total) / mean * 100 if mean else None
    drift = None
    pairs = [p for p in series if p.get("heart_rate_bpm") and p.get("speed_kmh", 0) and p.get("sample_seconds") and p.get("pace_sec_km")]
    coverage = sum(p["sample_seconds"] for p in pairs) / total if total else 0
    if timing_complete and total >= 1200 and coverage >= .75:
        halfway = total / 2
        groups = [[], []]
        cursor = 0
        for p in pairs:
            groups[0 if cursor < halfway else 1].append(p)
            cursor += p["sample_seconds"]
        ratios = []
        for group in groups:
            weight = sum(p["sample_seconds"] for p in group)
            hr_mean = sum(p["heart_rate_bpm"] * p["sample_seconds"] for p in group) / weight if weight else 0
            speed = sum(p["speed_kmh"] * p["sample_seconds"] for p in group) / weight if weight else 0
            ratios.append(hr_mean / speed if speed else None)
        if all(ratios):
            drift = round((ratios[1] / ratios[0] - 1) * 100, 2)
    # A sustained >=10-second interval, rather than a single noisy GPS instant.
    candidates = [v for v, dt in paced if dt >= 10]
    if not candidates and paced:
        window, seconds = [], 0
        for value, dt in paced:
            window.append((value, dt)); seconds += dt
            while len(window) > 1 and seconds - window[0][1] >= 10:
                seconds -= window.pop(0)[1]
            if seconds >= 10:
                candidates.append(sum(v * t for v, t in window) / seconds)
    return {"metrics": metrics, "max_heart_rate": max(hr) if hr else None,
            "min_elevation_m": min(elevations) if elevations else None,
            "max_elevation_m": max(elevations) if elevations else None,
            "best_pace_sec_km": round(min(candidates), 1) if candidates and timing_complete else None,
            "pace_variability_pct": round(cv, 2) if cv is not None and timing_complete else None,
            "heart_rate_drift_pct": drift,
            "metric_notes": ["평균은 유효한 시간 가중 표본으로 계산합니다. 없는 기기 지표는 추정하지 않습니다."]}
