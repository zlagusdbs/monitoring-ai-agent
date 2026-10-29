"""바깥으로 나가는 HTTPS 설정.

사내 게이트웨이가 TLS 를 가로채고, 그 인증서에 Authority Key Identifier 가 없다.
Python 3.13 부터 기본으로 켜지는 VERIFY_X509_STRICT 가 이것을 거부한다.
인증서 검증은 그대로 두고 그 검사만 끈다.
"""

import os
import ssl

import httpx

CA_BUNDLE = os.getenv("MON_CA_BUNDLE", "")


def verify() -> ssl.SSLContext | bool:
    if not CA_BUNDLE or not os.path.exists(CA_BUNDLE):
        return True
    ctx = ssl.create_default_context(cafile=CA_BUNDLE)
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


def async_client(**kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(verify=verify(), **kwargs)


def post(url: str, **kwargs):
    return httpx.post(url, verify=verify(), **kwargs)
