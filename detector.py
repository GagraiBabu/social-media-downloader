"""
Platform detection and URL normalization module.
Covers the 12 verified social media video platforms:
1. YouTube
2. Instagram
3. Facebook
4. TikTok
5. X / Twitter
6. Reddit
7. Pinterest
8. Dailymotion
9. Moj
10. Snapchat
11. LinkedIn
12. VK / VK Video
"""

import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from typing import Dict, Optional, Tuple


# Regex patterns matching domain variants and valid paths for each platform
PLATFORM_PATTERNS = {
    "youtube": [
        r"^(https?://)?(www\.|m\.|music\.)?youtube\.com/(watch\?.*v=|embed/|v/|shorts/|live/)([\w\-]+)",
        r"^(https?://)?youtu\.be/([\w\-]+)",
    ],
    "instagram": [
        r"^(https?://)?(www\.)?instagram\.com/(p|reel|tv|stories)/([\w\-]+)",
        r"^(https?://)?instagr\.am/(p|reel|tv)/([\w\-]+)",
    ],
    "facebook": [
        r"^(https?://)?(www\.|m\.|web\.)?facebook\.com/.*(videos/|watch/\?v=|reel/|story\.php\?)([\w\-]+)",
        r"^(https?://)?fb\.watch/([\w\-]+)",
        r"^(https?://)?(www\.)?fb\.com/.*",
    ],
    "tiktok": [
        r"^(https?://)?(www\.|m\.)?tiktok\.com/@[\w.\-]+/video/\d+",
        r"^(https?://)?(vm|vt)\.tiktok\.com/([\w\-]+)",
    ],
    "x_twitter": [
        r"^(https?://)?(www\.)?(twitter|x)\.com/[\w\-]+/status/(\d+)",
        r"^(https?://)?t\.co/([\w\-]+)",
    ],
    "reddit": [
        r"^(https?://)?(www\.|old\.|new\.)?reddit\.com/r/[\w\-]+/comments/[\w\-]+",
        r"^(https?://)?v\.redd\.it/([\w\-]+)",
        r"^(https?://)?redd\.it/([\w\-]+)",
    ],
    "pinterest": [
        r"^(https?://)?(www\.|[a-z]{2}\.)?pinterest\.[a-z.]+/pin/(\d+)",
        r"^(https?://)?pin\.it/([\w\-]+)",
    ],
    "dailymotion": [
        r"^(https?://)?(www\.)?dailymotion\.com/video/([\w\-]+)",
        r"^(https?://)?dai\.ly/([\w\-]+)",
    ],
    "moj": [
        r"^(https?://)?(www\.)?mojapp\.in/@[\w\-]+/video/([\w\-]+)",
        r"^(https?://)?(share\.)?mojapp\.in/([\w\-]+)",
    ],
    "snapchat": [
        r"^(https?://)?(www\.)?snapchat\.com/(spotlight|add|s)/([\w\-]+)",
    ],
    "linkedin": [
        r"^(https?://)?(www\.)?linkedin\.com/(posts|feed/update)/[\w.\-]+",
        r"^(https?://)?(www\.)?linkedin\.com/posts/[\w.\-]+_[\w\-]+-[\w\-]+",
    ],
}

# Tracking and analytics query parameters to strip during URL normalization
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "igsh", "si", "feature", "ref", "s", "t", "_r", "sender_device",
    "is_from_webapp", "share_id", "source"
}


def normalize_url(raw_url: str) -> str:
    """
    Normalizes a social media URL by:
    - Stripping trailing whitespace
    - Ensuring https scheme
    - Removing tracking query parameters (e.g., utm_*, fbclid, si)
    - Lowercasing the hostname
    """
    if not raw_url:
        return ""

    url = raw_url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parsed = urlparse(url)
        scheme = "https"
        netloc = parsed.netloc.lower()

        # Parse and filter query parameters
        query_dict = parse_qs(parsed.query, keep_blank_values=False)
        clean_query_dict = {
            k: v for k, v in query_dict.items() if k.lower() not in TRACKING_PARAMS
        }

        clean_query = urlencode(clean_query_dict, doseq=True)

        normalized = urlunparse((
            scheme,
            netloc,
            parsed.path,
            parsed.params,
            clean_query,
            ""  # Strip fragment (#)
        ))
        return normalized
    except Exception:
        return raw_url


def detect_platform(url: str) -> Tuple[Optional[str], bool, str]:
    """
    Detects the social media platform from the URL.

    Returns:
        (platform_name: Optional[str], is_valid: bool, normalized_url: str)
    """
    if not url or not isinstance(url, str):
        return None, False, ""

    norm_url = normalize_url(url)
    parsed = urlparse(norm_url)
    hostname = parsed.netloc.lower()

    if not hostname:
        return None, False, norm_url

    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, norm_url, re.IGNORECASE):
                return platform, True, norm_url

    # Fallback host domain checks if URL path variant was not covered by strict regex
    host_map = {
        "youtube.com": "youtube",
        "youtu.be": "youtube",
        "instagram.com": "instagram",
        "instagr.am": "instagram",
        "facebook.com": "facebook",
        "fb.watch": "facebook",
        "fb.com": "facebook",
        "tiktok.com": "tiktok",
        "twitter.com": "x_twitter",
        "x.com": "x_twitter",
        "reddit.com": "reddit",
        "redd.it": "reddit",
        "v.redd.it": "reddit",
        "pinterest.com": "pinterest",
        "pin.it": "pinterest",
        "dailymotion.com": "dailymotion",
        "dai.ly": "dailymotion",
        "mojapp.in": "moj",
        "snapchat.com": "snapchat",
        "linkedin.com": "linkedin",
        "vk.com": "vk",
        "vkvideo.ru": "vk",
    }

    for domain_suffix, platform in host_map.items():
        if hostname == domain_suffix or hostname.endswith("." + domain_suffix):
            return platform, True, norm_url

    return None, False, norm_url
