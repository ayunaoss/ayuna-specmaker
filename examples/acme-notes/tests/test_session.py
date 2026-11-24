"""Tests name the scenario IDs they prove, so `specmaker.py trace` can find them."""

import unittest
from datetime import datetime, timedelta, timezone

from notes.session import SessionExpired, SessionStore


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


class SessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.store = SessionStore(clock=self.clock)

    def test_sign_in_returns_token__SESS_01_1(self) -> None:
        """covers: SESS-01.1"""
        token = self.store.create("u1")
        self.assertEqual(self.store.validate(token), "u1")

    def test_active_session_continues_and_resets_timer__SESS_02_1(self) -> None:
        """covers: SESS-02.1"""
        token = self.store.create("u1")
        self.clock.advance(minutes=29)
        self.assertEqual(self.store.validate(token), "u1")
        self.clock.advance(minutes=29)  # timer was reset, so still valid
        self.assertEqual(self.store.validate(token), "u1")

    def test_idle_session_expires__SESS_02_3(self) -> None:
        """covers: SESS-02.3"""
        token = self.store.create("u1")
        self.clock.advance(minutes=30)
        with self.assertRaises(SessionExpired) as ctx:
            self.store.validate(token)
        self.assertEqual(ctx.exception.reason, "session_expired")

    def test_sign_out_invalidates__SESS_02_2(self) -> None:
        """covers: SESS-02.2"""
        token = self.store.create("u1")
        self.store.sign_out(token)
        with self.assertRaises(SessionExpired) as ctx:
            self.store.validate(token)
        self.assertEqual(ctx.exception.reason, "session_invalid")

    def test_absolute_lifetime_ends_active_session__SESS_03_1(self) -> None:
        """covers: SESS-03.1"""
        token = self.store.create("u1")
        for _ in range(24):  # stay active every 29 minutes for ~11.6 hours
            self.clock.advance(minutes=29)
            self.store.validate(token)
        self.clock.advance(minutes=29)  # crosses 12 hours since sign-in
        with self.assertRaises(SessionExpired) as ctx:
            self.store.validate(token)
        self.assertEqual(ctx.exception.reason, "session_lifetime_exceeded")


if __name__ == "__main__":
    unittest.main()
