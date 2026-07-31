# 일시정지·중지 공통 게이트 - 목록 수집(동기 Playwright)과 홈페이지·SNS
# 보강(asyncio) 양쪽에서 재사용한다. pause_event/stop_event는 threading.Event
# 그대로 받는다(ui.py가 이미 갖고 있는 것을 그대로 넘긴다 - 새 이벤트 타입을
# 만들지 않는다). 이미 시작된 요청을 취소하는 기능은 없다 - "다음 신규 작업을
# 시작하기 직전" 지점에서만 호출해 안전하게 대기시키는 것이 유일한 책임이다.
import asyncio


def wait_while_paused(pause_event, stop_event, poll_interval: float = 0.2) -> None:
    """동기 코드 전용. pause_event가 켜져 있는 동안 대기하다가 재개(clear)
    또는 중지(stop_event.set())되면 즉시 반환한다. stop_event.wait(timeout)을
    사용해 폴링 없이 깨어나므로 CPU를 busy-loop로 소모하지 않는다."""
    if pause_event is None:
        return
    while pause_event.is_set():
        if stop_event is not None and stop_event.is_set():
            return
        if stop_event is not None:
            stop_event.wait(poll_interval)
        else:
            pause_event.wait(poll_interval)


async def wait_while_paused_async(pause_event, stop_event, poll_interval: float = 0.2) -> None:
    """비동기 코드 전용(home_enrichment.py). asyncio.sleep으로 대기해 이벤트
    루프를 막지 않는다 - 동시성(semaphore) 처리 중인 다른 task를 방해하지
    않아야 하므로 wait_while_paused(blocking)를 그대로 쓰면 안 된다."""
    if pause_event is None:
        return
    while pause_event.is_set():
        if stop_event is not None and stop_event.is_set():
            return
        await asyncio.sleep(poll_interval)
