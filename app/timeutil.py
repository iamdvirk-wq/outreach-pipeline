"""Converting between stored UTC times and your local time zone."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app import config

LOCAL_TZ = ZoneInfo(config.TIMEZONE)


def to_local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)


def local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def local_midnight_utc(days_ago: int = 0) -> datetime:
    """Start of the local day (days_ago days back), as naive UTC for DB queries."""
    start = local_now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


def local_date_start_utc(d: datetime) -> datetime:
    """Midnight local time on the given calendar date, as naive UTC."""
    start = d.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=LOCAL_TZ)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


def local_week_start_utc() -> datetime:
    """Start of this local week (Monday), as naive UTC."""
    return local_midnight_utc(days_ago=local_now().weekday())


def fmt(dt: datetime | None, with_time: bool = True) -> str:
    d = to_local(dt)
    if d is None:
        return ""
    return d.strftime("%d %b %Y %H:%M" if with_time else "%d %b %Y")
