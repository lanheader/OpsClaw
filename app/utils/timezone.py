from datetime import datetime, timedelta, timezone

_BEIJING_TZ = timezone(timedelta(hours=8))


def get_beijing_now() -> datetime:
    return datetime.now(_BEIJING_TZ)
