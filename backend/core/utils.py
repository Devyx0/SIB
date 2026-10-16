from datetime import date, datetime
from zoneinfo import ZoneInfo
from .config import settings


def today_local() -> date:
    return datetime.now(ZoneInfo(settings.TIMEZONE)).date()
