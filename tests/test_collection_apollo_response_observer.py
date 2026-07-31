from pathlib import Path
import sys


# Apollo 목록 Network 응답 관찰 인프라(src/collection/apollo_response_observer.py의
# _classify_candidate_http_status/_QueryObservationContext/_make_response_handler/
# _make_request_finished_handler/_make_request_failed_handler) 계약 고정용
# standalone 스크립트. 이 파일은 다음 모듈 이동(Response Observer 분리) 전에
# 현재 동작(candidate 등록, body snapshot 성공/실패 경로, requestfailed 처리)을
# characterization test로 고정하는 것이 유일한 목적이며, 실제 Playwright
# page/response 객체는 전혀 다루지 않고 최소 Fake만 사용한다(실제 Playwright
# 접속 없음). 기존 tests/test_collection_apollo_list_collector.py의
# FakeRequest/FakeResponse와 의도적으로 독립적으로 재구현한다(파일 간 import
# 없음 - 기존 관례 그대로).
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.collection.apollo_response_observer import (
    _MAX_CANDIDATE_BODY_BYTES,
    _classify_candidate_http_status,
    _QueryObservationContext,
    _make_request_failed_handler,
    _make_request_finished_handler,
    _make_response_handler,
)


class ValidationReporter:
    def __init__(self):
        self.pass_count = 0
        self.fail_count = 0

    def pass_(self, message: str) -> None:
        self.pass_count += 1
        print(f"[PASS] {message}")

    def fail(self, message: str) -> None:
        self.fail_count += 1
        print(f"[FAIL] {message}")

    def summary(self) -> None:
        final = "FAIL" if self.fail_count else "PASS"
        print("====================")
        print(f"PASS: {self.pass_count}")
        print(f"FAIL: {self.fail_count}")
        print(f"FINAL: {final}")
        print("====================")


CANDIDATE_URL = "https://map.naver.com/graphql"
NON_CANDIDATE_URL = "https://map.naver.com/static/app.css"


class FakeRequest:
    """Observer가 실제로 접근하는 request 표면만 제공한다: url/resource_type/
    method/failure(속성), response()(메서드 - entry["response"]가 없을 때만
    fallback으로 호출됨). response_call_count로 호출 횟수를 명시적으로 센다."""

    def __init__(self, *, url=CANDIDATE_URL, resource_type="xhr", method="GET",
                 failure=None, response_obj=None, response_error=None):
        self.url = url
        self.resource_type = resource_type
        self.method = method
        self.failure = failure
        self._response_obj = response_obj
        self._response_error = response_error
        self.response_call_count = 0

    def response(self):
        self.response_call_count += 1
        if self._response_error is not None:
            raise self._response_error
        return self._response_obj


class FakeResponse:
    """Observer가 실제로 접근하는 response 표면만 제공한다: url/status/request
    (속성), headers(.get()을 지원하는 dict), body()/text()(메서드). body_call_count/
    text_call_count로 호출 횟수를 명시적으로 센다(§4/§5 조기 차단 검증에 필수)."""

    def __init__(self, url, status, request, *, headers=None,
                 body_bytes=None, body_error=None, text_value=None, text_error=None):
        self.url = url
        self.status = status
        self.request = request
        self.headers = headers if headers is not None else {}
        self._body_bytes = body_bytes
        self._body_error = body_error
        self._text_value = text_value
        self._text_error = text_error
        self.body_call_count = 0
        self.text_call_count = 0

    def body(self):
        self.body_call_count += 1
        if self._body_error is not None:
            raise self._body_error
        return self._body_bytes

    def text(self):
        self.text_call_count += 1
        if self._text_error is not None:
            raise self._text_error
        return self._text_value


def check_classify_candidate_http_status_contract(reporter: ValidationReporter) -> None:
    """1. _classify_candidate_http_status의 독립 계약: 2xx는 빈 문자열,
    429/그 외 실패 상태는 "CandidateHttpError", status=None은 빈 문자열
    (response를 전혀 받지 못한 requestfailed 전용 synthetic entry 대비)."""
    ok = (
        _classify_candidate_http_status(200) == ""
        and _classify_candidate_http_status(299) == ""
        and _classify_candidate_http_status(429) == "CandidateHttpError"
        and _classify_candidate_http_status(500) == "CandidateHttpError"
        and _classify_candidate_http_status(199) == "CandidateHttpError"
        and _classify_candidate_http_status(300) == "CandidateHttpError"
        and _classify_candidate_http_status(None) == ""
    )
    if ok:
        reporter.pass_("1. _classify_candidate_http_status: 2xx=빈문자열, 429/실패=CandidateHttpError, None=빈문자열")
    else:
        reporter.fail(
            "1. classify 계약 실패: "
            f"200={_classify_candidate_http_status(200)!r}, 429={_classify_candidate_http_status(429)!r}, "
            f"500={_classify_candidate_http_status(500)!r}, None={_classify_candidate_http_status(None)!r}"
        )


def check_candidate_registration_dedup_and_ambiguous(reporter: ValidationReporter) -> None:
    """2. candidate 등록 계약: (a) 유효 candidate는 정확히 1건 등록되고
    candidate_response_count가 1 증가하며 id(request)로 candidate에 역참조할 수
    있다 - 초기 entry는 body_snapshot_ready=False/body_snapshot=None/
    candidate_error_type=classify(status) 상태로 시작한다. (b) 같은 response
    객체가 다시 전달되면(중복 이벤트) 두 번째 entry를 만들지 않는다(idempotent
    dedup). (c) 같은 request가 이미 candidate로 등록된 상태에서 다른 response로
    재차 도착하면(ambiguous) 두 번째 entry를 만들지 않고
    ambiguous_request_mapping_count만 증가시킨다."""
    ctx = _QueryObservationContext()
    response_handler = _make_response_handler(ctx)

    request = FakeRequest()
    response = FakeResponse(CANDIDATE_URL, 200, request)
    response_handler(response)

    registration_ok = (
        len(ctx.candidates) == 1
        and ctx.candidate_response_count == 1
        and id(request) in ctx.request_id_to_candidate
        and ctx.request_id_to_candidate[id(request)] is ctx.candidates[0]
    )
    entry = ctx.candidates[0] if ctx.candidates else {}
    initial_state_ok = (
        entry.get("response") is response
        and entry.get("body_snapshot") is None
        and entry.get("body_snapshot_ready") is False
        and entry.get("body_snapshot_error_type") == ""
        and entry.get("candidate_error_type") == _classify_candidate_http_status(200)
    )

    response_handler(response)  # 동일 response 재전달 -> dedupe(등록 개수 불변)
    dedup_ok = len(ctx.candidates) == 1 and ctx.candidate_response_count == 1

    other_response = FakeResponse(CANDIDATE_URL, 200, request)  # 같은 request, 다른 response
    response_handler(other_response)
    ambiguous_ok = (
        len(ctx.candidates) == 1
        and ctx.candidate_response_count == 1
        and ctx.ambiguous_request_mapping_count == 1
    )

    ok = registration_ok and initial_state_ok and dedup_ok and ambiguous_ok
    if ok:
        reporter.pass_("2. candidate 등록: 1건 등록+count 증가+id(request) 역참조, 중복 response는 dedup, ambiguous request는 카운터만 증가")
    else:
        reporter.fail(
            "2. candidate 등록 계약 실패: "
            f"registration_ok={registration_ok}, initial_state_ok={initial_state_ok}, "
            f"dedup_ok={dedup_ok}, ambiguous_ok={ambiguous_ok}, candidates={ctx.candidates}"
        )


def check_body_snapshot_success(reporter: ValidationReporter) -> None:
    """3. 정상 body snapshot 저장: response.body()가 반환한 bytes가 그대로
    body_snapshot에 저장되고 body_snapshot_ready=True, 오류 상태는 빈 문자열,
    body()는 정확히 1회만 호출되며 text()는 호출되지 않는다. content-type
    헤더도 entry에 그대로 반영된다."""
    ctx = _QueryObservationContext()
    payload = b'{"result":{"place":{"list":[]}}}'
    request = FakeRequest()
    response = FakeResponse(
        CANDIDATE_URL, 200, request,
        headers={"content-type": "application/json"}, body_bytes=payload,
    )
    _make_response_handler(ctx)(response)
    try:
        _make_request_finished_handler(ctx)(request)
    except Exception as exc:
        reporter.fail(f"3. 정상 snapshot 처리 중 예외가 밖으로 전파됨: {exc}")
        return

    entry = ctx.request_id_to_candidate[id(request)]
    ok = (
        entry["body_snapshot"] == payload
        and entry["body_snapshot_ready"] is True
        and entry["body_snapshot_error_type"] == ""
        and entry["body_snapshot_size"] == len(payload)
        and entry["content_type"] == "application/json"
        and response.body_call_count == 1
        and response.text_call_count == 0
    )
    if ok:
        reporter.pass_("3. 정상 body snapshot: bytes 저장 + ready=True + body() 1회 호출 + text() 미호출")
    else:
        reporter.fail(f"3. 정상 snapshot 계약 실패: entry={entry}, body_calls={response.body_call_count}, text_calls={response.text_call_count}")


def check_content_length_early_rejection(reporter: ValidationReporter) -> None:
    """4. content-length 헤더가 _MAX_CANDIDATE_BODY_BYTES를 초과하면 body()
    자체를 호출하지 않고(할당 자체를 막기 위함) 즉시 BodyTooLarge로 조기
    차단한다 - text() fallback도 실행하지 않는다. snapshot은 저장되지 않고
    ready 상태도 False로 남는다."""
    ctx = _QueryObservationContext()
    oversized = _MAX_CANDIDATE_BODY_BYTES + 1
    request = FakeRequest()
    response = FakeResponse(
        CANDIDATE_URL, 200, request,
        headers={"content-length": str(oversized)},
        body_bytes=b"should never be read",
    )
    _make_response_handler(ctx)(response)
    try:
        _make_request_finished_handler(ctx)(request)
    except Exception as exc:
        reporter.fail(f"4. content-length 조기 차단 중 예외가 밖으로 전파됨: {exc}")
        return

    entry = ctx.request_id_to_candidate[id(request)]
    ok = (
        entry["body_snapshot_error_type"] == "BodyTooLarge"
        and entry["body_snapshot_ready"] is False
        and entry["body_snapshot"] is None
        and entry["body_snapshot_size"] == oversized
        and str(oversized) in entry["body_snapshot_error_message"]
        and response.body_call_count == 0
        and response.text_call_count == 0
    )
    if ok:
        reporter.pass_("4. content-length 초과: body()/text() 전혀 호출하지 않고 즉시 BodyTooLarge로 조기 차단")
    else:
        reporter.fail(
            f"4. content-length 조기 차단 계약 실패: entry={entry}, "
            f"body_calls={response.body_call_count}, text_calls={response.text_call_count}"
        )


def check_actual_body_size_too_large(reporter: ValidationReporter) -> None:
    """5. content-length 헤더가 없어 조기 차단되지 않았지만, 실제로 읽은
    body가 _MAX_CANDIDATE_BODY_BYTES를 초과하면(사후 판정, line 299 분기)
    BodyTooLarge로 기록한다 - 이 분기는 Check 4(조기 차단, body() 미호출)와
    달리 body()가 실제로 1회 호출된 뒤에 판정된다는 점이 유일한 차이다."""
    ctx = _QueryObservationContext()
    oversized_body = b"x" * (_MAX_CANDIDATE_BODY_BYTES + 1)
    request = FakeRequest()
    response = FakeResponse(CANDIDATE_URL, 200, request, headers={}, body_bytes=oversized_body)
    _make_response_handler(ctx)(response)
    try:
        _make_request_finished_handler(ctx)(request)
    except Exception as exc:
        reporter.fail(f"5. 실제 body 크기 과대 처리 중 예외가 밖으로 전파됨: {exc}")
        return

    entry = ctx.request_id_to_candidate[id(request)]
    ok = (
        entry["body_snapshot_error_type"] == "BodyTooLarge"
        and entry["body_snapshot_ready"] is False
        and entry["body_snapshot"] is None
        and entry["body_snapshot_size"] == len(oversized_body)
        and str(len(oversized_body)) in entry["body_snapshot_error_message"]
        and response.body_call_count == 1
        and response.text_call_count == 0
    )
    if ok:
        reporter.pass_("5. content-length 없이 실제 body가 상한 초과: body() 1회 호출 후 BodyTooLarge로 사후 차단(조기 차단과 구분됨)")
    else:
        reporter.fail(
            f"5. 실제 body 크기 과대 계약 실패: entry={entry}, "
            f"body_calls={response.body_call_count}, text_calls={response.text_call_count}"
        )


def check_empty_body_is_not_success(reporter: ValidationReporter) -> None:
    """6. body()가 0바이트(b"")를 반환하면 성공으로 취급하지 않고 EmptyBody로
    기록한다(json.loads(b"")가 항상 실패하므로 JSON decode 실패로 미루지 않고
    이 시점에 확정) - snapshot은 저장되지 않고 예외도 전파되지 않는다."""
    ctx = _QueryObservationContext()
    request = FakeRequest()
    response = FakeResponse(CANDIDATE_URL, 200, request, headers={}, body_bytes=b"")
    _make_response_handler(ctx)(response)
    try:
        _make_request_finished_handler(ctx)(request)
    except Exception as exc:
        reporter.fail(f"6. 빈 body 처리 중 예외가 밖으로 전파됨: {exc}")
        return

    entry = ctx.request_id_to_candidate[id(request)]
    ok = (
        entry["body_snapshot_error_type"] == "EmptyBody"
        and entry["body_snapshot_error_message"] == "response body가 0바이트입니다"
        and entry["body_snapshot_ready"] is False
        and entry["body_snapshot"] is None
        and entry["body_snapshot_size"] == 0
        and response.body_call_count == 1
        and response.text_call_count == 0
    )
    if ok:
        reporter.pass_("6. body()가 0바이트 반환: EmptyBody로 기록(성공 처리 안 함), 예외 전파 없음")
    else:
        reporter.fail(f"6. 빈 body 계약 실패: entry={entry}")


def check_text_fallback_when_body_raises(reporter: ValidationReporter) -> None:
    """7. response.body() 호출이 예외를 던지면 response.text().encode("utf-8")로
    fallback한다(성공 시 snapshot 저장) - text()마저 실패하면 그 예외의
    type(exc).__name__을 body_snapshot_error_type으로 기록한다(둘 다 실패하는
    경로도 예외를 밖으로 던지지 않는다)."""
    ctx = _QueryObservationContext()

    request_a = FakeRequest()
    fallback_text = "café 한글 텍스트"
    response_a = FakeResponse(
        CANDIDATE_URL, 200, request_a, headers={},
        body_error=RuntimeError("body unavailable"), text_value=fallback_text,
    )
    _make_response_handler(ctx)(response_a)
    try:
        _make_request_finished_handler(ctx)(request_a)
    except Exception as exc:
        reporter.fail(f"7. text() fallback 성공 경로에서 예외가 밖으로 전파됨: {exc}")
        return
    entry_a = ctx.request_id_to_candidate[id(request_a)]
    fallback_success_ok = (
        entry_a["body_snapshot"] == fallback_text.encode("utf-8")
        and entry_a["body_snapshot_ready"] is True
        and entry_a["body_snapshot_error_type"] == ""
        and response_a.body_call_count == 1
        and response_a.text_call_count == 1
    )

    request_b = FakeRequest()
    response_b = FakeResponse(
        CANDIDATE_URL, 200, request_b, headers={},
        body_error=RuntimeError("body unavailable"), text_error=ValueError("text also fails"),
    )
    _make_response_handler(ctx)(response_b)
    try:
        _make_request_finished_handler(ctx)(request_b)
    except Exception as exc:
        reporter.fail(f"7. text() fallback도 실패하는 경로에서 예외가 밖으로 전파됨: {exc}")
        return
    entry_b = ctx.request_id_to_candidate[id(request_b)]
    fallback_failure_ok = (
        entry_b["body_snapshot_error_type"] == "ValueError"
        and entry_b["body_snapshot_error_message"] == "text also fails"
        and entry_b["body_snapshot_ready"] is False
        and response_b.body_call_count == 1
        and response_b.text_call_count == 1
    )

    ok = fallback_success_ok and fallback_failure_ok
    if ok:
        reporter.pass_("7. body() 예외 시 text().encode('utf-8')로 fallback 성공, text()마저 실패하면 그 예외 타입으로 기록(예외 전파 없음)")
    else:
        reporter.fail(f"7. text() fallback 계약 실패: fallback_success_ok={fallback_success_ok}, fallback_failure_ok={fallback_failure_ok}, entry_a={entry_a}, entry_b={entry_b}")


def _make_placeholder_entry(request, *, response=None) -> dict:
    """response 부재(Check 8) 검증 전용 - response handler를 거치지 않고
    entry["response"]=None 상태를 직접 구성한다(코드 주석상 "entry["response"]가
    없는 경우(예: 향후 다른 등록 경로)에 한해서만 fallback으로 사용" - 현재
    response handler는 항상 response를 채우므로 이 분기는 정상 흐름에서
    도달하지 않는다. 이 분기 자체를 보호하려면 handler를 직접 이 상태로
    호출해야 한다)."""
    return {
        "sequence_id": 0, "response": response, "request": request, "url": CANDIDATE_URL,
        "method": "GET", "resource_type": "xhr", "status": None, "content_type": "",
        "content_encoding": "", "body_snapshot": None, "body_snapshot_ready": False,
        "body_snapshot_error_type": "", "body_snapshot_error_message": "",
        "body_snapshot_size": 0, "json_top_level_type": "", "json_decode_error_type": "",
        "candidate_error_type": "", "processed": False, "generation": 1,
    }


def check_no_response_handling(reporter: ValidationReporter) -> None:
    """8. entry["response"]가 없는 경우(현재 구현의 fallback 경로) request.
    response()를 재조회한다 - (a) 재조회 자체가 예외를 던지면 그 예외의
    type(exc).__name__을 기록하고, (b) 재조회가 None을 반환하면 "NoResponse"로
    기록한다. 두 경로 모두 예외를 밖으로 던지지 않는다."""
    ctx_a = _QueryObservationContext()
    request_a = FakeRequest(response_error=RuntimeError("response gone"))
    entry_a = _make_placeholder_entry(request_a)
    ctx_a.candidates.append(entry_a)
    ctx_a.request_id_to_candidate[id(request_a)] = entry_a
    try:
        _make_request_finished_handler(ctx_a)(request_a)
    except Exception as exc:
        reporter.fail(f"8. request.response() 예외 경로에서 예외가 밖으로 전파됨: {exc}")
        return
    response_error_ok = (
        entry_a["body_snapshot_error_type"] == "RuntimeError"
        and entry_a["body_snapshot_error_message"] == "response gone"
        and entry_a["body_snapshot_ready"] is False
        and request_a.response_call_count == 1
    )

    ctx_b = _QueryObservationContext()
    request_b = FakeRequest(response_obj=None)
    entry_b = _make_placeholder_entry(request_b)
    ctx_b.candidates.append(entry_b)
    ctx_b.request_id_to_candidate[id(request_b)] = entry_b
    try:
        _make_request_finished_handler(ctx_b)(request_b)
    except Exception as exc:
        reporter.fail(f"8. request.response()가 None을 반환하는 경로에서 예외가 밖으로 전파됨: {exc}")
        return
    no_response_ok = (
        entry_b["body_snapshot_error_type"] == "NoResponse"
        and entry_b["body_snapshot_error_message"] == "request.response()가 None을 반환함"
        and entry_b["body_snapshot_ready"] is False
        and request_b.response_call_count == 1
    )

    ok = response_error_ok and no_response_ok
    if ok:
        reporter.pass_("8. response 부재: request.response() 예외는 그 타입명으로, None 반환은 NoResponse로 기록(예외 전파 없음)")
    else:
        reporter.fail(f"8. response 부재 계약 실패: response_error_ok={response_error_ok}, no_response_ok={no_response_ok}, entry_a={entry_a}, entry_b={entry_b}")


def check_request_failed_handler_contract(reporter: ValidationReporter) -> None:
    """9. requestfailed 처리: (a) 이미 등록된 candidate가 실패하면
    body_snapshot_error_type="RequestFailed" + failure 메시지가 기록되고,
    무관한 다른 candidate는 영향받지 않는다. (b) 한 번도 등록된 적 없는
    request도 candidate URL/resource_type 패턴과 일치하면 새 entry를 만들어
    같은 방식으로 기록한다(§response handler와 동일한 is_candidate_response
    판정 재사용). (c) candidate 패턴과 무관한 request는 무시되며 기존
    candidate를 오염시키지 않는다(이 handler에는 response/requestfinished
    handler의 unmatched/ambiguous 카운터에 대응하는 카운터가 없다 - 대신
    "무시되고 기존 상태를 바꾸지 않는다"는 사실 자체가 보호 대상이다)."""
    ctx = _QueryObservationContext()
    response_handler = _make_response_handler(ctx)
    failed_handler = _make_request_failed_handler(ctx)

    request1 = FakeRequest(url=CANDIDATE_URL, failure="net::ERR_CONNECTION_RESET")
    response1 = FakeResponse(CANDIDATE_URL, 200, request1)
    response_handler(response1)

    request2 = FakeRequest(url=CANDIDATE_URL)  # 무관한(성공한) 다른 candidate
    response2 = FakeResponse(CANDIDATE_URL, 200, request2)
    response_handler(response2)

    try:
        failed_handler(request1)
    except Exception as exc:
        reporter.fail(f"9. 등록된 candidate의 requestfailed 처리 중 예외가 밖으로 전파됨: {exc}")
        return

    entry1 = ctx.request_id_to_candidate[id(request1)]
    entry2 = ctx.request_id_to_candidate[id(request2)]
    registered_failure_ok = (
        entry1["body_snapshot_error_type"] == "RequestFailed"
        and entry1["body_snapshot_error_message"] == "net::ERR_CONNECTION_RESET"
        and entry2["body_snapshot_error_type"] == ""  # 무관한 candidate는 영향받지 않음
        and len(ctx.candidates) == 2
    )

    request3 = FakeRequest(url=CANDIDATE_URL, resource_type="xhr", failure="net::ERR_ABORTED")
    try:
        failed_handler(request3)
    except Exception as exc:
        reporter.fail(f"9. 미등록 candidate-패턴 request 처리 중 예외가 밖으로 전파됨: {exc}")
        return
    unregistered_candidate_ok = (
        len(ctx.candidates) == 3
        and id(request3) in ctx.request_id_to_candidate
        and ctx.request_id_to_candidate[id(request3)]["body_snapshot_error_type"] == "RequestFailed"
        and ctx.request_id_to_candidate[id(request3)]["body_snapshot_error_message"] == "net::ERR_ABORTED"
    )

    request4 = FakeRequest(url=NON_CANDIDATE_URL, resource_type="stylesheet", failure="net::ERR_ABORTED")
    try:
        failed_handler(request4)
    except Exception as exc:
        reporter.fail(f"9. 무관한 request 처리 중 예외가 밖으로 전파됨: {exc}")
        return
    unrelated_request_ignored_ok = (
        len(ctx.candidates) == 3  # 새 entry가 생기지 않음
        and id(request4) not in ctx.request_id_to_candidate
        and ctx.request_id_to_candidate[id(request1)]["body_snapshot_error_type"] == "RequestFailed"
        and ctx.request_id_to_candidate[id(request2)]["body_snapshot_error_type"] == ""
    )

    ok = registered_failure_ok and unregistered_candidate_ok and unrelated_request_ignored_ok
    if ok:
        reporter.pass_("9. requestfailed: 등록된 candidate만 실패 기록, 미등록 candidate-패턴은 신규 entry 생성, 무관한 request는 무시(기존 candidate 오염 없음)")
    else:
        reporter.fail(
            "9. requestfailed 계약 실패: "
            f"registered_failure_ok={registered_failure_ok}, unregistered_candidate_ok={unregistered_candidate_ok}, "
            f"unrelated_request_ignored_ok={unrelated_request_ignored_ok}, candidates={ctx.candidates}"
        )


def main() -> bool:
    reporter = ValidationReporter()
    checks = [
        check_classify_candidate_http_status_contract,
        check_candidate_registration_dedup_and_ambiguous,
        check_body_snapshot_success,
        check_content_length_early_rejection,
        check_actual_body_size_too_large,
        check_empty_body_is_not_success,
        check_text_fallback_when_body_raises,
        check_no_response_handling,
        check_request_failed_handler_contract,
    ]
    for check in checks:
        check(reporter)
    reporter.summary()
    return reporter.fail_count == 0


def test_apollo_response_observer_contract():
    assert main() is True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
