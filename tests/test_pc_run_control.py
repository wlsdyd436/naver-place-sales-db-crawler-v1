"""단위 테스트: src/pc/run_control.wait_while_paused/wait_while_paused_async
(NETWORK-CONTROLS-1 - 일시정지 중 대기, 재개/중지 시 즉시 반환하는 공통
게이트). 실제 Playwright/네이버 요청 없이 threading.Event/asyncio만으로
검증한다."""
import asyncio
import sys
import threading
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.run_control import wait_while_paused, wait_while_paused_async  # noqa: E402

_POLL = 0.05


def test_wait_while_paused_returns_immediately_when_not_paused():
    pause_event = threading.Event()
    stop_event = threading.Event()
    started = time.monotonic()
    wait_while_paused(pause_event, stop_event, poll_interval=_POLL)
    assert time.monotonic() - started < 0.1


def test_wait_while_paused_none_pause_event_returns_immediately():
    stop_event = threading.Event()
    started = time.monotonic()
    wait_while_paused(None, stop_event, poll_interval=_POLL)
    assert time.monotonic() - started < 0.1


def test_wait_while_paused_blocks_until_resumed():
    pause_event = threading.Event()
    stop_event = threading.Event()
    pause_event.set()

    def _resume_after_delay():
        time.sleep(0.15)
        pause_event.clear()

    threading.Thread(target=_resume_after_delay, daemon=True).start()
    started = time.monotonic()
    wait_while_paused(pause_event, stop_event, poll_interval=_POLL)
    elapsed = time.monotonic() - started
    assert elapsed >= 0.1, "재개 전에 너무 일찍 반환되면 안 됨"
    assert elapsed < 1.0, "재개 후에는 곧바로 반환돼야 함(무한 대기 아님)"


def test_wait_while_paused_stop_wins_while_paused():
    pause_event = threading.Event()
    stop_event = threading.Event()
    pause_event.set()

    def _stop_after_delay():
        time.sleep(0.1)
        stop_event.set()

    threading.Thread(target=_stop_after_delay, daemon=True).start()
    started = time.monotonic()
    wait_while_paused(pause_event, stop_event, poll_interval=_POLL)
    elapsed = time.monotonic() - started
    assert elapsed < 0.5
    # 중지가 우선하므로 pause_event 자체는 여전히 set 상태로 남아있어도 된다
    # (재개 여부와 무관하게 즉시 빠져나오는 것이 계약).
    assert stop_event.is_set()


def test_wait_while_paused_async_returns_immediately_when_not_paused():
    async def _run():
        pause_event = threading.Event()
        stop_event = threading.Event()
        started = time.monotonic()
        await wait_while_paused_async(pause_event, stop_event, poll_interval=_POLL)
        return time.monotonic() - started

    assert asyncio.run(_run()) < 0.1


def test_wait_while_paused_async_none_pause_event_returns_immediately():
    async def _run():
        started = time.monotonic()
        await wait_while_paused_async(None, threading.Event(), poll_interval=_POLL)
        return time.monotonic() - started

    assert asyncio.run(_run()) < 0.1


def test_wait_while_paused_async_blocks_until_resumed():
    async def _run():
        pause_event = threading.Event()
        stop_event = threading.Event()
        pause_event.set()

        async def _resume_after_delay():
            await asyncio.sleep(0.15)
            pause_event.clear()

        asyncio.create_task(_resume_after_delay())
        started = time.monotonic()
        await wait_while_paused_async(pause_event, stop_event, poll_interval=_POLL)
        return time.monotonic() - started

    elapsed = asyncio.run(_run())
    assert elapsed >= 0.1
    assert elapsed < 1.0


def test_wait_while_paused_async_stop_wins_while_paused():
    async def _run():
        pause_event = threading.Event()
        stop_event = threading.Event()
        pause_event.set()

        async def _stop_after_delay():
            await asyncio.sleep(0.1)
            stop_event.set()

        asyncio.create_task(_stop_after_delay())
        started = time.monotonic()
        await wait_while_paused_async(pause_event, stop_event, poll_interval=_POLL)
        return time.monotonic() - started

    assert asyncio.run(_run()) < 0.5


def test_wait_while_paused_does_not_hold_lock_forever_when_never_resumed_and_stopped_immediately():
    """무한 대기 방지 확인 - stop_event가 이미 set된 상태로 들어오면 pause
    중이어도 즉시 반환해야 한다(호출자가 재개를 잊어도 앱이 멈추지 않음)."""
    pause_event = threading.Event()
    stop_event = threading.Event()
    pause_event.set()
    stop_event.set()
    started = time.monotonic()
    wait_while_paused(pause_event, stop_event, poll_interval=_POLL)
    assert time.monotonic() - started < 0.1
