from datetime import datetime, time
import zoneinfo
from typing import Optional
from .config import settings

class SystemClock:
    def __init__(self):
        self._override_dt: Optional[datetime] = None
        if settings.clock_override:
            try:
                self.set_override(settings.clock_override)
            except Exception:
                pass

    @property
    def timezone(self):
        try:
            return zoneinfo.ZoneInfo(settings.scheduler_timezone)
        except Exception:
            try:
                return zoneinfo.ZoneInfo("UTC")
            except Exception:
                from datetime import timezone, timedelta
                if "kolkata" in settings.scheduler_timezone.lower():
                    return timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
                return timezone.utc

    def now(self) -> datetime:
        if self._override_dt is not None:
            return self._override_dt
        return datetime.now(self.timezone)

    def iso_now(self) -> str:
        return self.now().isoformat()

    def set_override(self, dt_str: Optional[str]):
        if not dt_str:
            self._override_dt = None
        else:
            parsed = datetime.fromisoformat(dt_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=self.timezone)
            else:
                parsed = parsed.astimezone(self.timezone)
            self._override_dt = parsed

    def is_override_active(self) -> bool:
        return self._override_dt is not None

    def is_within_business_hours(self, dt: Optional[datetime] = None) -> bool:
        check_time = dt if dt is not None else self.now()
        # Weekday: Monday is 0, Sunday is 6
        if check_time.weekday() not in settings.business_days:
            return False

        start_h, start_m = map(int, settings.business_hours_start.split(":"))
        end_h, end_m = map(int, settings.business_hours_end.split(":"))

        window_start = time(start_h, start_m)
        window_end = time(end_h, end_m)

        current_time = check_time.time()
        return window_start <= current_time <= window_end

clock = SystemClock()
