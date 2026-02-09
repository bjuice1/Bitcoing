"""Background scheduler for periodic metric fetching."""
import logging
import threading
import schedule
import time

logger = logging.getLogger("btcmonitor.scheduler")


class MonitorScheduler:
    def __init__(self, monitor, interval_seconds=900):
        self.monitor = monitor
        self.interval = interval_seconds
        self._thread = None
        self._running = False
        self._callbacks = []
        self._weekly_callbacks = []
        self._last_weekly_send = None
        self._consecutive_failures = 0

    def on_fetch(self, callback):
        """Register callback called after each successful fetch."""
        self._callbacks.append(callback)

    def on_weekly(self, callback):
        """Register callback fired once on Sundays (weekly digest, etc.)."""
        self._weekly_callbacks.append(callback)

    def start(self):
        """Start background fetching."""
        if self._running:
            return
        self._running = True

        schedule.every(self.interval).seconds.do(self._fetch_job)

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"Scheduler started (every {self.interval}s)")

    def stop(self):
        """Stop background fetching."""
        self._running = False
        schedule.clear()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Scheduler stopped")

    def _run_loop(self):
        # Do an initial fetch immediately
        self._fetch_job()
        while self._running:
            schedule.run_pending()
            self._check_weekly()
            time.sleep(1)

    def _check_weekly(self):
        """Fire weekly callbacks once on Sundays."""
        from datetime import date
        today = date.today()
        if today.weekday() == 6 and self._last_weekly_send != today:
            self._last_weekly_send = today
            for cb in self._weekly_callbacks:
                try:
                    cb()
                except Exception as e:
                    logger.warning(f"Weekly callback error: {e}")

    def _fetch_job(self):
        try:
            snapshot = self.monitor.fetch_and_store()
            self._consecutive_failures = 0
            for cb in self._callbacks:
                try:
                    cb(snapshot)
                except Exception as e:
                    logger.warning(f"Callback error: {e}")
        except Exception as e:
            self._consecutive_failures += 1
            logger.error(f"Fetch failed ({self._consecutive_failures} consecutive): {e}")
            if self._consecutive_failures >= 5:
                logger.critical("5+ consecutive fetch failures!")
