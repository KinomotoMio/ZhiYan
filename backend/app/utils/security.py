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

            # Check for private, loopback, link-local, multicast, etc.
            if (ip.is_private or
                ip.is_loopback or
                ip.is_link_local or
                ip.is_multicast or
                ip.is_unspecified or
                ip.is_reserved):
                return False

            # Check for IPv4-mapped IPv6 addresses (::ffff:192.168.0.1)
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                mapped_ip = ip.ipv4_mapped
                if (mapped_ip.is_private or
                    mapped_ip.is_loopback or
                    mapped_ip.is_link_local or
                    mapped_ip.is_multicast or
                    mapped_ip.is_unspecified or
                    mapped_ip.is_reserved):
                    return False
        return True
    except Exception:
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
    event_hooks = kwargs.get("event_hooks", {})
    if "request" not in event_hooks:
        event_hooks["request"] = []

    # Add our validation hook to the list
    event_hooks["request"].append(validate_url_hook)
    kwargs["event_hooks"] = event_hooks

    return httpx.AsyncClient(**kwargs)
