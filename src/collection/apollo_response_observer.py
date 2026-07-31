# Apollo 후보 response/request 생명주기를 관찰하는 모듈. 입력은 Playwright형
# response/request 이벤트 객체(page.on("response"/"requestfinished"/
# "requestfailed")가 전달하는 것과 동일한 duck-typed 표면)이며, 출력은
# _QueryObservationContext에 축적되는 candidate 상태(entry dict 목록)다.
# candidate 판별은 place_mapper.is_candidate_response를 그대로 재사용한다
# (재구현 없음). 이 모듈은 페이지 이동, listener 등록·해제(page.on/page.off),
# candidate body의 JSON list 파싱, row 변환, 필터, BrowserSession 수명 관리를
# 전혀 수행하지 않는다 - 그 책임은 전부 apollo_list_collector.py에 남는다.
from src.collection.place_mapper import is_candidate_response

# PAGE-300-2B-2B: candidate response body의 안전 상한(바이트). PAGE-300-2B-2A
# 실측(page 2 candidate 응답 약 414KB)보다 넉넉한 여유를 두되, 메모리 폭주를
# 막기 위한 상한이다 - 초과하면 body 자체는 저장하지 않고 에러로만 기록한다.
_MAX_CANDIDATE_BODY_BYTES = 2 * 1024 * 1024


def _classify_candidate_http_status(status) -> str:
    """PAGE-300-2B-4A(gpt-5.6-sol 독립 검토 지적, Medium 반영): status는
    response 이벤트 시점에 이미 알 수 있으므로, body snapshot 성공/실패와
    무관하게 candidate 등록 즉시 분류한다 - 이전에는 이 판정이
    body_snapshot_ready 분기 안에만 있어 EmptyBody/BodyTooLarge/RequestFailed
    등으로 snapshot 자체가 실패한 non-2xx candidate(예: HTTP 429 + 빈 body)가
    candidate_http_error_count/candidate_http_status_counts에 전혀 반영되지
    않았다(안전성에는 영향 없음 - candidate_snapshot_error로 이미 pagination이
    중단되지만, 진단 완전성이 떨어졌다). status가 None이면(예: response를
    전혀 받지 못한 requestfailed 전용 synthetic entry) 빈 문자열을 반환한다."""
    if status is not None and not (200 <= status <= 299):
        return "CandidateHttpError"
    return ""


class _QueryObservationContext:
    """쿼리 1회 호출에 국한된 로컬 상태(전역/클래스 공용 상태를 두지 않기 위함).

    handler는 이 인스턴스에만 기록하며, 쿼리 1건 처리가 끝나면
    함께 버려진다 - 다음 쿼리는 항상 새 인스턴스로 시작하므로 이전 쿼리의
    응답과 섞이지 않는다(페이지 자체도 WIRE-2B부터는 쿼리마다 새로 생성/종료될
    예정이라 이중으로 격리된다).
    """

    def __init__(self):
        # PAGE-300-2B-2B: candidate 하나당 raw response 객체 대신 candidate
        # entry(dict)를 담는다(§candidate entry 계약) - 인덱스 순서(도착 순서)
        # 의미는 기존과 동일하게 유지하면서, 내용물만 "나중에 body에 다시
        # 접근 가능한 response 객체"에서 "이미 확보한 snapshot(bytes) 여부를
        # 담은 entry"로 바뀐다.
        self.candidates: list = []
        self.candidate_response_count = 0
        self.status_429_seen = False
        # PAGE-300-2B-1-FIX §3: 같은 response 객체가 브라우저에서 'response'
        # 이벤트를 중복 발생시키는 극단적인 경우에도 object identity(id())로
        # 한 번만 기록한다 - 인덱스가 아니라 객체 자체를 키로 써야, 동일 객체가
        # 두 번 append돼 서로 다른 인덱스로 두 번 harvest(JSON parse 2회)되는
        # 것을 막을 수 있다. response 객체는 candidates에 계속 참조로 남아있으므로
        # (쿼리 종료 전까지) id() 재사용(GC) 위험이 없다.
        self.seen_response_ids: set = set()
        # PAGE-300-2B-2B: requestfinished/requestfailed는 request 객체를 받으므로
        # (response가 아니라), id(request) -> candidate entry로 역참조할 수 있어야
        # 한다. response 이벤트가 먼저 도착해 candidate로 판별될 때만 이 맵에
        # 등록되므로, candidate가 아닌 request는 이 맵에 없고 두 핸들러는 즉시
        # no-op으로 반환한다.
        self.request_id_to_candidate: dict = {}
        # PAGE-300-2B-2B: 순수 진단용 로컬 라벨(§candidate entry의 generation) -
        # "지금까지 확정된 페이지 수 + 1"을 기록할 뿐, response 내용으로 실제
        # 네이버 page를 추측하는 것과 무관하다(우리가 클릭을 시도한 시점 기준
        # 로컬 카운터일 뿐이라 "페이지 번호 추측 금지" 원칙과 충돌하지 않는다).
        self.current_generation = 1
        # PAGE-300-2B-2D §5: request-response 연결 무결성 진단. 정상 경로에서는
        # 항상 0이어야 하며, 0보다 크면 candidate identity 매칭이 깨졌다는 뜻이다.
        self.unmatched_requestfinished_count = 0
        self.ambiguous_request_mapping_count = 0


def _make_response_handler(ctx: _QueryObservationContext):
    """response handler는 최소 작업만 한다(상태 확인 + candidate entry 등록) -
    PAGE-300-2B-2B: body snapshot도 JSON 파싱도 이 handler에서 하지 않는다
    (response 본문을 읽는 메서드는 전혀 호출하지 않음 - 정적 검사로 회귀
    고정). body snapshot은 requestfinished handler가, JSON 파싱은 harvest
    단계가 각각 책임진다."""

    def handle_response(response) -> None:
        try:
            if response.status == 429:
                ctx.status_429_seen = True
        except Exception:
            pass

        try:
            request = response.request
        except Exception:
            request = None

        try:
            resource_type = request.resource_type if request is not None else ""
        except Exception:
            resource_type = ""
        url = response.url or ""

        try:
            if is_candidate_response(url, resource_type):
                response_id = id(response)
                if response_id in ctx.seen_response_ids:
                    return
                ctx.seen_response_ids.add(response_id)
                # 방어적 dedupe: 같은 request가 이미 candidate로 등록돼 있으면
                # (이론상 발생하지 않아야 하지만) entry를 중복 생성하지 않는다.
                # PAGE-300-2B-2D §5: 이 경우가 바로 "하나의 request가 둘 이상의
                # response/candidate에 연결되려는" ambiguous 상황이다 - 두 번째
                # entry를 만들지 않음으로써 "snapshot을 성공 처리하지 않음"
                # 요구사항을 이미 만족하며, 여기서는 그 사실을 진단 카운터로
                # 남긴다.
                if request is not None and id(request) in ctx.request_id_to_candidate:
                    ctx.ambiguous_request_mapping_count += 1
                    return
                try:
                    status = response.status
                except Exception:
                    status = None
                try:
                    method = request.method if request is not None else ""
                except Exception:
                    method = ""
                entry = {
                    "sequence_id": ctx.candidate_response_count,
                    "response": response,
                    "request": request,
                    "url": url,
                    "method": method,
                    "resource_type": resource_type,
                    "status": status,
                    "content_type": "",
                    "content_encoding": "",
                    "body_snapshot": None,
                    "body_snapshot_ready": False,
                    "body_snapshot_error_type": "",
                    "body_snapshot_error_message": "",
                    "body_snapshot_size": 0,
                    "json_top_level_type": "",
                    "json_decode_error_type": "",
                    "candidate_error_type": _classify_candidate_http_status(status),
                    "processed": False,
                    "generation": ctx.current_generation,
                }
                ctx.candidates.append(entry)
                ctx.candidate_response_count += 1
                if request is not None:
                    ctx.request_id_to_candidate[id(request)] = entry
        except Exception:
            pass

    return handle_response


def _make_request_finished_handler(ctx: _QueryObservationContext):
    """PAGE-300-2B-2B: requestfinished 시점에 candidate body를 즉시 bytes로
    snapshot한다(PAGE-300-2B-2A 실측 원인 - 지연된 시점의 response.json()/
    body()는 "Response body is unavailable"로 실패할 수 있으므로, 완료
    직후 안전한 시점에만 접근한다). candidate가 아닌 request는 즉시 무시하고,
    이미 resolve된 entry(중복 이벤트)도 idempotent하게 무시한다. 어떤 예외도
    밖으로 던지지 않는다."""

    def handle_request_finished(request) -> None:
        try:
            entry = ctx.request_id_to_candidate.get(id(request))
            if entry is None:
                # PAGE-300-2B-2D §5: candidate로 등록된 적 없는 request의
                # requestfinished는 대부분 정상이다(이미지/스크립트 등 애초에
                # candidate가 아닌 리소스도 requestfinished를 발생시킨다).
                # candidate URL/resource_type 패턴과 일치하는데도 매핑이 없는
                # 경우에만 진짜 이상 신호(연결 실패)로 집계한다.
                try:
                    unmatched_url = request.url or ""
                except Exception:
                    unmatched_url = ""
                try:
                    unmatched_resource_type = request.resource_type
                except Exception:
                    unmatched_resource_type = ""
                if is_candidate_response(unmatched_url, unmatched_resource_type):
                    ctx.unmatched_requestfinished_count += 1
                return
            if entry["body_snapshot_ready"] or entry["body_snapshot_error_type"]:
                return
            # PAGE-300-2B-2D(gpt-5.6-sol 독립 검토 지적, High): request.response()를
            # 다시 호출하면, 이 request 객체가 (이론상 발생하지 않아야 하지만)
            # candidate 등록 이후 다른 response를 참조하도록 바뀌었을 경우 이
            # entry의 메타데이터(url/status 등은 candidate A)와 실제로 snapshot되는
            # body(response B)가 서로 다른 candidate의 것으로 뒤섞일 수 있다.
            # entry["response"]는 candidate 등록 시점(response handler)에 이미
            # 확정된 참조이므로 이를 우선 사용해 정체성을 고정한다 - request.
            # response()로의 재조회는 entry["response"]가 없는 경우(예: 향후
            # 다른 등록 경로)에 한해서만 fallback으로 사용한다.
            response = entry.get("response")
            if response is None:
                try:
                    response = request.response()
                except Exception as exc:
                    entry["body_snapshot_error_type"] = type(exc).__name__
                    entry["body_snapshot_error_message"] = str(exc)[:200]
                    return
            if response is None:
                entry["body_snapshot_error_type"] = "NoResponse"
                entry["body_snapshot_error_message"] = "request.response()가 None을 반환함"
                return
            # PAGE-300-2B-2B(gpt-5.6-sol 독립 검토 지적): response.body()는
            # 전체 body를 메모리에 만든 뒤에야 길이를 알 수 있어 크기 검사
            # 만으로는 할당 자체를 막지 못한다 - content-length 헤더를 먼저
            # 확인할 수 있으면 body()를 아예 호출하지 않고 조기에 거른다
            # (헤더가 없거나 파싱 불가하면 기존처럼 body() 이후 길이로만 판단).
            try:
                entry["content_type"] = response.headers.get("content-type") or ""
            except Exception:
                entry["content_type"] = ""
            try:
                entry["content_encoding"] = response.headers.get("content-encoding") or ""
            except Exception:
                entry["content_encoding"] = ""
            try:
                content_length_header = response.headers.get("content-length")
            except Exception:
                content_length_header = None
            if content_length_header is not None:
                try:
                    content_length = int(content_length_header)
                except (TypeError, ValueError):
                    content_length = None
                if content_length is not None and content_length > _MAX_CANDIDATE_BODY_BYTES:
                    entry["body_snapshot_error_type"] = "BodyTooLarge"
                    entry["body_snapshot_error_message"] = (
                        f"content-length {content_length} bytes exceeds {_MAX_CANDIDATE_BODY_BYTES} bytes cap"
                    )
                    entry["body_snapshot_size"] = content_length
                    return
            try:
                body = response.body()
            except Exception:
                try:
                    body = response.text().encode("utf-8")
                except Exception as exc2:
                    entry["body_snapshot_error_type"] = type(exc2).__name__
                    entry["body_snapshot_error_message"] = str(exc2)[:200]
                    return
            # PAGE-300-2B-2D §3: 빈 body(0바이트)는 성공이 아니다 - json.loads(b"")는
            # 항상 실패하므로 JSON decode 실패로 미루지 않고 이 시점에 별도
            # 오류 타입으로 확정한다(PAGE-300-2B-2C의 "success_count=2인데
            # total_bytes가 page1 크기만"이던 모순의 유력 원인 - 빈 snapshot이
            # 성공으로 잘못 집계됐을 가능성).
            if len(body) == 0:
                entry["body_snapshot_error_type"] = "EmptyBody"
                entry["body_snapshot_error_message"] = "response body가 0바이트입니다"
                entry["body_snapshot_size"] = 0
                return
            if len(body) > _MAX_CANDIDATE_BODY_BYTES:
                entry["body_snapshot_error_type"] = "BodyTooLarge"
                entry["body_snapshot_error_message"] = (
                    f"{len(body)} bytes exceeds {_MAX_CANDIDATE_BODY_BYTES} bytes cap"
                )
                entry["body_snapshot_size"] = len(body)
                return
            entry["body_snapshot"] = body
            entry["body_snapshot_ready"] = True
            entry["body_snapshot_size"] = len(body)
        except Exception:
            pass

    return handle_request_finished


def _make_request_failed_handler(ctx: _QueryObservationContext):
    """PAGE-300-2B-2B: requestfailed 시점에 candidate를 실패로 표시한다(retry는
    하지 않는다 - 사실만 기록). idempotent하게, 이미 resolve된 entry는
    건드리지 않는다.

    gpt-5.6-sol 독립 검토 지적(2차) 반영: response를 전혀 받지 못하고 실패한
    request는 'response' 이벤트가 한 번도 발생하지 않으므로
    ctx.request_id_to_candidate에 등록될 기회가 없었다 - 다른 candidate가
    정상 성공해 per_query_limit에 도달하면 이 실패가 진단에서 완전히
    사라져(parse_error_count/body_snapshot_error_count 어디에도 반영되지
    않음) 거짓 성공처럼 보일 위험이 있었다. 이제 등록된 적 없는 request도
    request.url/resource_type만으로 candidate 여부를 판별해(§response
    handler와 동일한 is_candidate_response 판정 - response 객체 접근은
    필요 없다), candidate였다면 실패 entry를 새로 만들어 harvest 시점에
    parse_error_count/body_snapshot_error_count에 반영되게 한다."""

    def handle_request_failed(request) -> None:
        try:
            entry = ctx.request_id_to_candidate.get(id(request))
            if entry is not None:
                if entry["body_snapshot_ready"] or entry["body_snapshot_error_type"]:
                    return
            else:
                try:
                    url = request.url or ""
                except Exception:
                    url = ""
                try:
                    resource_type = request.resource_type
                except Exception:
                    resource_type = ""
                if not is_candidate_response(url, resource_type):
                    return
                try:
                    method = request.method
                except Exception:
                    method = ""
                entry = {
                    "sequence_id": ctx.candidate_response_count,
                    "response": None,
                    "request": request,
                    "url": url,
                    "method": method,
                    "resource_type": resource_type,
                    "status": None,
                    "content_type": "",
                    "content_encoding": "",
                    "body_snapshot": None,
                    "body_snapshot_ready": False,
                    "body_snapshot_error_type": "",
                    "body_snapshot_error_message": "",
                    "body_snapshot_size": 0,
                    "json_top_level_type": "",
                    "json_decode_error_type": "",
                    "candidate_error_type": "",
                    "processed": False,
                    "generation": ctx.current_generation,
                }
                ctx.candidates.append(entry)
                ctx.candidate_response_count += 1
                ctx.request_id_to_candidate[id(request)] = entry

            entry["body_snapshot_error_type"] = "RequestFailed"
            try:
                failure = request.failure
                message = str(failure) if failure else ""
            except Exception:
                message = ""
            entry["body_snapshot_error_message"] = message[:200]
        except Exception:
            pass

    return handle_request_failed
