import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

URLPolicy = Literal["resolved_ip", "https_domain_only"]

STRICT_POLICY_ERROR = "访问被拒绝: 不允许向内部或私有地址发送请求"
HTTPS_DOMAIN_POLICY_ERROR = (
    "访问被拒绝: 仅支持使用 https 的域名地址进行校验，不允许 localhost 或 IP 地址"
)

_DOMAIN_LABEL_RE = re.compile(r"^[A-Za-z0-9-]{1,63}$")
_LOCAL_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "localhost6",
    "ip6-localhost",
    "ip6-loopback",
    "loopback",
}


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def _is_local_hostname(hostname: str) -> bool:
    normalized = hostname.rstrip(".").lower()
    return normalized in _LOCAL_HOSTNAMES or normalized.endswith(".localhost")


def _is_domain_hostname(hostname: str) -> bool:
    normalized = hostname.rstrip(".")
    if "." not in normalized:
        return False

    labels = normalized.split(".")
    return all(
        label
        and not label.startswith("-")
        and not label.endswith("-")
        and _DOMAIN_LABEL_RE.fullmatch(label)
        for label in labels
    )


def _allows_https_domain_only(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False

    hostname = parsed.hostname
    if not hostname or _is_local_hostname(hostname) or _is_ip_literal(hostname):
        return False

    return _is_domain_hostname(hostname)


async def _allows_resolved_ip(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    loop = asyncio.get_running_loop()
    ips = await loop.getaddrinfo(hostname, None)
    for res in ips:
        ip_str = res[4][0]
        ip = ipaddress.ip_address(ip_str)
        if not ip.is_global:
            return False
    return True


async def is_safe_url(url: str, url_policy: URLPolicy = "resolved_ip") -> bool:
    """
    Check whether a URL is safe for server-side requests under the selected policy.
    """
    try:
        if url_policy == "resolved_ip":
            return await _allows_resolved_ip(url)
        if url_policy == "https_domain_only":
            return _allows_https_domain_only(url)
        raise ValueError(f"Unsupported URL policy: {url_policy}")
    except (socket.gaierror, ValueError):
        return False


def _build_policy_error(request: httpx.Request, url_policy: URLPolicy) -> str:
    prefix = STRICT_POLICY_ERROR if url_policy == "resolved_ip" else HTTPS_DOMAIN_POLICY_ERROR
    return f"{prefix} ({request.url})"


def build_validate_url_hook(
    url_policy: URLPolicy = "resolved_ip",
) -> Callable[[httpx.Request], Awaitable[None]]:
    async def _validate_url_hook(request: httpx.Request) -> None:
        if not await is_safe_url(str(request.url), url_policy=url_policy):
            raise HTTPException(
                status_code=400,
                detail=_build_policy_error(request, url_policy),
            )

    return _validate_url_hook


async def validate_url_hook(request: httpx.Request) -> None:
    """
    httpx request hook to validate the URL before sending the request.
    """
    hook = build_validate_url_hook()
    await hook(request)


def get_safe_httpx_client(
    *, url_policy: URLPolicy = "resolved_ip", **kwargs
) -> httpx.AsyncClient:
    """
    Return an httpx.AsyncClient with SSRF protection enabled via request hooks.
    """
    hooks = kwargs.pop("event_hooks", {}).copy()
    request_hooks = hooks.get("request", []).copy()
    request_hooks.append(build_validate_url_hook(url_policy=url_policy))
    hooks["request"] = request_hooks
    return httpx.AsyncClient(event_hooks=hooks, **kwargs)
