"""Analytics / dashboard metrics."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import require_operator
from ..database import get_db
from ..models import Entry, EntryType, Incident, IncidentStatus, NUMERIC_ENTRY_TYPES, User
from ..schemas import AnalyticsOverview, CallerStat, TrendPoint, TypeCount, TypeTotal

router = APIRouter(prefix="/analytics", tags=["analytics"])


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
