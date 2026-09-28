"""HTTP transport restricted to the app's local model engine.

Do not inherit corporate/system proxies or follow a redirect away from loopback.
This transport is also used for the actual RAG inference, not just warmup.
"""
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


def validate_endpoint(endpoint: str) -> str:
    value = urlsplit(endpoint)
    if (value.scheme != "http" or value.hostname != "127.0.0.1"
            or value.username is not None or value.password is not None
            or not value.port or value.port == 11434
            or value.path not in ("", "/") or value.query or value.fragment):
        raise ValueError("앱이 소유한 내부 CPU 엔진 주소만 사용할 수 있습니다.")
    return endpoint.rstrip("/")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("내부 AI 엔진의 주소 변경 요청을 차단했습니다.")


def open_local(request, timeout=180):
    value = urlsplit(request.full_url)
    validate_endpoint(f"{value.scheme}://{value.netloc}")
    return build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout)
