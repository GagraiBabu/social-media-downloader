"""
Security utility module for Social Media Video Downloader.
Handles URL validation, SSRF protection, and path/filename sanitization.
"""

import ipaddress
import re
import socket
from urllib.parse import urlparse
from typing import Tuple


# Allowed schemes for media URLs
ALLOWED_SCHEMES = {"http", "https"}

# Blocked IP ranges to prevent Server-Side Request Forgery (SSRF)
BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("10.0.0.0/8"),        # Private network RFC1918
    ipaddress.ip_network("172.16.0.0/12"),     # Private network RFC1918
    ipaddress.ip_network("192.168.0.0/16"),    # Private network RFC1918
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local / AWS metadata
    ipaddress.ip_network("0.0.0.0/8"),         # Current network
    ipaddress.ip_network("100.64.0.0/10"),     # Shared address space
    ipaddress.ip_network("198.18.0.0/15"),     # Benchmark testing
    ipaddress.ip_network("::1/128"),           # IPv6 Loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 Unique Local
    ipaddress.ip_network("fe80::/10"),         # IPv6 Link-Local
]


def validate_url_security(url: str) -> Tuple[bool, str]:
    """
    Validates that a URL is safe to process:
    - Must be a non-empty string
    - Must use http or https scheme
    - Must have a valid network location (domain/host)
    - Must NOT resolve to private, loopback, or cloud-metadata IP addresses (SSRF defense)
    
    Returns:
        (is_safe: bool, error_message: str)
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string"

    url = url.strip()
    if len(url) > 2048:
        return False, "URL exceeds maximum allowed length of 2048 characters"

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Malformed URL structure"

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return False, f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL does not contain a valid hostname"

    # Reject localhost directly
    if hostname.lower() in {"localhost", "localhost.localdomain", "broadcasthost"}:
        return False, "Requests to localhost are blocked for security"

    # Resolve hostname to IP to protect against SSRF (internal networks and cloud metadata)
    try:
        # getaddrinfo returns list of (family, type, proto, canonname, sockaddr)
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        resolved_ips = set()
        for item in addr_info:
            ip_str = item[4][0]
            resolved_ips.add(ip_str)

        for ip_str in resolved_ips:
            ip_obj = ipaddress.ip_address(ip_str)
            for blocked_net in BLOCKED_IP_NETWORKS:
                if ip_obj in blocked_net:
                    return False, f"Access to private/internal network IP ({ip_str}) is forbidden"

            # Double check with ipaddress built-in properties
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
                return False, f"Access to restricted IP ({ip_str}) is forbidden"

    except socket.gaierror:
        return False, f"Cannot resolve hostname '{hostname}'. Host does not exist or DNS lookup failed."
    except Exception as e:
        return False, f"Host validation error: {str(e)}"

    return True, ""


def sanitize_filename(name: str, fallback: str = "video.mp4") -> str:
    """
    Sanitizes an extracted title or filename to prevent directory traversal
    or invalid characters on Linux and Windows filesystems.
    """
    if not name:
        return fallback

    # Strip directory paths
    clean = re.sub(r"[\\/*?:\'\"<>|]", "_", name)
    # Remove control chars and non-printable characters
    clean = "".join(c for c in clean if c.isprintable())
    # Strip dangerous leading or trailing characters
    clean = clean.strip(". _-")
    # Limit length
    if len(clean) > 120:
        clean = clean[:120]

    return clean if clean else fallback
