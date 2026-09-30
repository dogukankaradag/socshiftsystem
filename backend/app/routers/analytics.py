"""Analytics / dashboard metrics."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import require_operator
from ..database import get_db
from ..models import Entry, EntryType, Incident, IncidentStatus, NUMERIC_ENTRY_TYPES, User
from ..schemas import AnalyticsOverview, CallerStat, TrendPoint, TypeCount, TypeTotal

router = APIRouter(prefix="/analytics", tags=["analytics"])


# v0.9.17: Zaman aralığı → gün sayısı. "all" için None döner (filtresiz).
RANGE_DAYS: dict[str, Optional[int]] = {
    "week": 7,
    "month": 30,
    "3month": 90,
    "6month": 180,
    "year": 365,
    "all": None,
}


def _range_start(range_key: str) -> Optional[datetime]:
    days = RANGE_DAYS.get(range_key, 30)
    if days is None:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


@router.get("/overview", response_model=AnalyticsOverview)
def overview(db: Session = Depends(get_db), _=Depends(require_operator)):
    # counts by type
    by_type_rows = (
        db.query(Entry.entry_type, func.count(Entry.id))
        .group_by(Entry.entry_type)
        .all()
    )
    by_type = [TypeCount(entry_type=t, count=c) for t, c in by_type_rows]

    total_entries = db.query(func.count(Entry.id)).scalar() or 0
    open_incidents = (
        db.query(func.count(Incident.id))
        .filter(Incident.status.in_([IncidentStatus.open, IncidentStatus.in_progress]))
        .scalar()
        or 0
    )
    now = datetime.now(timezone.utc)
    upcoming_count = (
        db.query(func.count(Entry.id))
        .filter(Entry.occurs_at.isnot(None))
        .filter(Entry.occurs_at > now)
        .scalar()
        or 0
    )

    # 14-day trend (yalnızca toplam)
    today = now.date()
    start = today - timedelta(days=13)
    trend_rows = (
        db.query(Entry.created_at)
        .filter(Entry.created_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc))
        .all()
    )
    buckets: dict[str, int] = {}
    for i in range(14):
        d = (start + timedelta(days=i)).isoformat()
        buckets[d] = 0
    for (created_at,) in trend_rows:
        d = created_at.date().isoformat()
        if d in buckets:
            buckets[d] += 1
    trend = [TrendPoint(date=k, total=v) for k, v in sorted(buckets.items())]

    # 30-day totals per entry type
    recent_start = now - timedelta(days=30)
    totals_rows = (
        db.query(
            Entry.entry_type,
            func.count(Entry.id),
            func.coalesce(func.sum(Entry.numeric_value), 0),
        )
        .filter(Entry.created_at >= recent_start)
        .group_by(Entry.entry_type)
        .all()
    )
    totals_30d_map: dict[EntryType, TypeTotal] = {}
    for t, count, num_sum in totals_rows:
        if t in NUMERIC_ENTRY_TYPES:
            total = int(num_sum or 0)
        else:
            total = int(count or 0)
        totals_30d_map[t] = TypeTotal(entry_type=t, count=int(count or 0), total=total)
    totals_30d = []
    for t in EntryType:
        if t in totals_30d_map:
            totals_30d.append(totals_30d_map[t])
        else:
            totals_30d.append(TypeTotal(entry_type=t, count=0, total=0))

    # Recurring titles (last 30 days, kept for trend insight)
    recent_titles = db.query(Entry.title).filter(Entry.created_at >= recent_start).all()
    title_counter: Counter[str] = Counter()
    for (title,) in recent_titles:
        if title:
            title_counter[title.strip().lower()] += 1
    recurring = [{"title": t, "count": c} for t, c in title_counter.most_common(10) if c >= 2]

    # v0.6.1: "Arayanlar" girişlerinin kullanıcı bazlı 30-günlük dağılımı.
    # Performans değerlendirmesi için — hangi operatör kaç çağrı aldı.
    callers_rows = (
        db.query(User.id, User.full_name, func.count(Entry.id))
        .join(Entry, Entry.author_id == User.id)
        .filter(Entry.entry_type == EntryType.callers)
        .filter(Entry.created_at >= recent_start)
        .group_by(User.id, User.full_name)
        .order_by(func.count(Entry.id).desc())
        .all()
    )
    callers_by_user = [
        CallerStat(user_id=int(uid), user_name=name, count=int(cnt))
        for uid, name, cnt in callers_rows
    ]

    return AnalyticsOverview(
        total_entries=int(total_entries),
        open_incidents=int(open_incidents),
        upcoming_count=int(upcoming_count),
        entries_by_type=by_type,
        trend_14d=trend,
        totals_30d=totals_30d,
        top_tags=[],
        recurring_titles=recurring,
        callers_by_user_30d=callers_by_user,
    )


# ==========================================================================
# v0.9.17: Yeni gelişmiş analitik endpoint — zaman aralığı + kişi bazlı
# performans + aylık dağılım. Frontend Analitik sayfasında dropdown ile
# haftalık/aylık/3ay/6ay/yıllık/tüm zamanlar seçilir.
# ==========================================================================

class MonthlyBucket(BaseModel):
    month: str  # "YYYY-MM"
    total: int


class TypeCountItem(BaseModel):
    entry_type: EntryType
    count: int
    numeric_total: int  # numeric_value toplamı (DHS/İYS için)


class UserPerfItem(BaseModel):
    user_id: int
    user_name: str
    total_entries: int
    by_type: dict[str, int]  # {'ddos_transfer': 5, 'callers': 12, ...}


class RangedAnalytics(BaseModel):
    range: str
    start_date: Optional[str]  # ISO
    end_date: str  # ISO (now)
    total_entries: int
    open_incidents: int
    upcoming_count: int
    entries_by_type: list[TypeCountItem]
    monthly_distribution: list[MonthlyBucket]
    per_user: list[UserPerfItem]
    top_callers: list[CallerStat]  # kim kaç Arayanlar girişi yaptı
    recurring_titles: list[dict]


@router.get("/ranged", response_model=RangedAnalytics)
def ranged_analytics(
    range: Literal["week", "month", "3month", "6month", "year", "all"] = Query("month"),
    db: Session = Depends(get_db),
    _=Depends(require_operator),
):
    """v0.9.17: Zaman aralığı filtrelenmiş kapsamlı analitik. Panel'in
    Analitik sayfasında kullanılır."""
    now = datetime.now(timezone.utc)
    start = _range_start(range)

    def _apply_range(q):
        if start is not None:
            return q.filter(Entry.created_at >= start)
        return q

    total_entries = _apply_range(db.query(func.count(Entry.id))).scalar() or 0

    open_incidents = (
        db.query(func.count(Incident.id))
        .filter(Incident.status.in_([IncidentStatus.open, IncidentStatus.in_progress]))
        .scalar()
        or 0
    )
    upcoming_count = (
        db.query(func.count(Entry.id))
        .filter(Entry.occurs_at.isnot(None))
        .filter(Entry.occurs_at > now)
        .scalar()
        or 0
    )

    # Tür bazlı: count + numeric_value toplamı
    by_type_rows = (
        _apply_range(
            db.query(
                Entry.entry_type,
                func.count(Entry.id),
                func.coalesce(func.sum(Entry.numeric_value), 0),
            )
        )
        .group_by(Entry.entry_type)
        .all()
    )
    by_type_map = {
        t: TypeCountItem(entry_type=t, count=int(c or 0), numeric_total=int(nt or 0))
        for t, c, nt in by_type_rows
    }
    entries_by_type = [
        by_type_map.get(t, TypeCountItem(entry_type=t, count=0, numeric_total=0))
        for t in EntryType
    ]

    # Aylık dağılım (YYYY-MM)
    monthly_rows = _apply_range(
        db.query(Entry.created_at)
    ).all()
    monthly_map: dict[str, int] = {}
    for (created_at,) in monthly_rows:
        key = created_at.strftime("%Y-%m")
        monthly_map[key] = monthly_map.get(key, 0) + 1
    monthly_distribution = [
        MonthlyBucket(month=k, total=v)
        for k, v in sorted(monthly_map.items())
    ]

    # Kişi bazlı toplam performans + tür kırılımı
    user_rows = (
        _apply_range(
            db.query(
                User.id,
                User.full_name,
                Entry.entry_type,
                func.count(Entry.id),
            )
            .join(Entry, Entry.author_id == User.id)
        )
        .group_by(User.id, User.full_name, Entry.entry_type)
        .all()
    )
    user_map: dict[int, dict] = {}
    for uid, name, etype, cnt in user_rows:
        if uid not in user_map:
            user_map[uid] = {
                "user_id": int(uid),
                "user_name": name or f"#{uid}",
                "total_entries": 0,
                "by_type": {},
            }
        c = int(cnt or 0)
        user_map[uid]["total_entries"] += c
        etype_val = etype.value if hasattr(etype, "value") else str(etype)
        user_map[uid]["by_type"][etype_val] = c
    per_user = [
        UserPerfItem(**u)
        for u in sorted(user_map.values(), key=lambda x: x["total_entries"], reverse=True)
    ]

    # Top callers (Arayanlar özel)
    caller_rows = (
        _apply_range(
            db.query(User.id, User.full_name, func.count(Entry.id))
            .join(Entry, Entry.author_id == User.id)
            .filter(Entry.entry_type == EntryType.callers)
        )
        .group_by(User.id, User.full_name)
        .order_by(func.count(Entry.id).desc())
        .all()
    )
    top_callers = [
        CallerStat(user_id=int(uid), user_name=name or f"#{uid}", count=int(cnt))
        for uid, name, cnt in caller_rows
    ]

    # Tekrarlayan başlıklar
    title_rows = _apply_range(db.query(Entry.title)).all()
    title_counter: Counter[str] = Counter()
    for (title,) in title_rows:
        if title:
            title_counter[title.strip().lower()] += 1
    recurring = [
        {"title": t, "count": c}
        for t, c in title_counter.most_common(20)
        if c >= 2
    ]

    return RangedAnalytics(
        range=range,
        start_date=start.isoformat() if start else None,
        end_date=now.isoformat(),
        total_entries=int(total_entries),
        open_incidents=int(open_incidents),
        upcoming_count=int(upcoming_count),
        entries_by_type=entries_by_type,
        monthly_distribution=monthly_distribution,
        per_user=per_user,
        top_callers=top_callers,
        recurring_titles=recurring,
    )
