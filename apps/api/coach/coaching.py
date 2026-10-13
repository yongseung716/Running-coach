import math
from datetime import date, datetime, timedelta, timezone

VERSION = "rules-1.0.0"


def prescribe(profile: dict, analyses: list[dict], today: date | None = None):
    today = today or datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=today.weekday())
    recent = []
    for a in analyses:
        try:
            day = datetime.fromisoformat(a["started_at"]).date()
        except (TypeError, ValueError, KeyError):
            continue
        if 0 <= (today - day).days < 28 and a.get("timing_complete") and a.get("distance_km", 0) > 0:
            recent.append((day, a))
    km28 = sum(a["distance_km"] for _, a in recent)
    km7 = sum(a["distance_km"] for d, a in recent if (today - d).days < 7)
    days_requested = max(2, min(5, profile.get("runs_per_week", 3)))
    experienced = len(recent) >= 6 and len({(today - d).days // 7 for d, _ in recent}) >= 3
    returning = bool(recent) and km7 == 0
    base = min(km28 / 4, km7) if km7 else km28 / 4 * 0.5
    target = math.floor(base * 1.05 * 100) / 100 if base else None
    if not recent:
        days_requested = min(days_requested, 3)
    slots = {2: [1, 5], 3: [0, 2, 5], 4: [0, 2, 4, 6], 5: [0, 1, 3, 4, 6]}[days_requested]
    days = []
    weights = [1] * (len(slots) - 1) + [1.4]
    distances = [math.floor(target * w / sum(weights) * 100) / 100 for w in weights] if target else []
    if distances:
        distances[-1] = round(target - sum(distances[:-1]), 2)
    for i in range(7):
        if i not in slots:
            days.append({"day_index": i, "date": (week_start + timedelta(days=i)).isoformat(),
                         "type": "rest", "title": "회복", "distance_km": None, "duration_min": None,
                         "instruction": "휴식 또는 편안한 걷기. 피로가 남으면 충분히 쉬세요."})
            continue
        position = slots.index(i)
        quality = experienced and not returning and km7 >= 10 and position == 1
        days.append({"day_index": i, "date": (week_start + timedelta(days=i)).isoformat(),
                     "type": "steady" if quality else "easy", "title": "편안한 지속주" if quality else "이지런 / 걷기",
                     "distance_km": distances[position] if distances else None,
                     "duration_min": None if target else 15,
                     "instruction": "대화가 가능한 강도. 필요하면 달리기와 걷기를 번갈아 하세요. " +
                                    ("중간 5분만 편안하게 리듬을 올리고 전력 질주는 피하세요." if quality else "거리보다 편안한 호흡을 우선하세요.")})
    goal = None
    if profile.get("goal_distance_km") and profile.get("goal_time_min"):
        goal = round(profile["goal_time_min"] * 60 / profile["goal_distance_km"], 1)
    return {"version": VERSION, "week_start": week_start.isoformat(), "days": days,
            "basis": {"valid_runs_28d": len(recent), "distance_28d_km": round(km28, 2),
                      "distance_7d_km": round(km7, 2), "weekly_target_km": target, "goal_pace_sec_km": goal},
            "explanation": "최근 28일 주간 평균과 최근 7일 중 작은 훈련량을 기준으로 최대 5%만 늘립니다." if km7 else
                           ("훈련 공백이 있어 최근 주간 평균의 절반부터 복귀합니다." if returning else "유효한 훈련 이력이 부족해 15분 달리기/걷기로 시작합니다."),
            "limitations": ["결측 시간·미래 기록은 처방 근거에서 제외됩니다.", "목표 페이스는 참고값이며 훈련 강도를 강제하지 않습니다.",
                            "의료 진단이나 부상 치료 처방이 아닙니다. 통증·흉통·어지럼증이 있으면 중단하고 전문가와 상담하세요."]}
