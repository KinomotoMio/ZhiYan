import asyncio
import ipaddress
import socket
from urllib.parse import urlparse
import httpx
from fastapi import HTTPException

async def is_safe_url(url: str) -> bool:
    """
    Checks if a URL is safe for server-side requests.
    Validates scheme and ensures the resolved IP is not a private or loopback address.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        # Resolve all IPs for the hostname asynchronously
        # socket.getaddrinfo returns a list of 5-tuples: (family, type, proto, canonname, sockaddr)
        # sockaddr is (address, port) for IPv4 and (address, port, flow info, scope id) for IPv6
        loop = asyncio.get_running_loop()
        ips = await loop.getaddrinfo(hostname, None)
        for res in ips:
            ip_str = res[4][0]
            ip = ipaddress.ip_address(ip_str)

            if not ip.is_global:
                return False
        return True
    except (socket.gaierror, ValueError):
        # If anything goes wrong during parsing or resolution, assume unsafe
        return False

async def validate_url_hook(request: httpx.Request):
    """
    httpx request hook to validate the URL before sending the request.
    """
    if not await is_safe_url(str(request.url)):
        raise HTTPException(
            status_code=400,
            detail=f"访问被拒绝: 不允许向内部或私有地址发送请求 ({request.url})"
        )

def get_safe_httpx_client(**kwargs) -> httpx.AsyncClient:
    """
    Returns an httpx.AsyncClient with SSRF protection enabled via request hooks.
    """
    hooks = kwargs.pop("event_hooks", {}).copy()
    request_hooks = hooks.get("request", []).copy()

    if validate_url_hook not in request_hooks:
        request_hooks.append(validate_url_hook)

    hooks["request"] = request_hooks

    return httpx.AsyncClient(event_hooks=hooks, **kwargs)
