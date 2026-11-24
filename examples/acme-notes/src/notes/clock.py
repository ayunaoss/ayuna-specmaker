"""Injectable clock (S3, ADR-0002). Production uses UTC wall time; tests pass a fake."""

from datetime import datetime, timezone
from typing import Callable

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
