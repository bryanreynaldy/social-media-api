import re
import json
import requests
import pandas as pd
import numpy as np
import asyncio
import sys
import subprocess
import os
import time
import random
import getpass
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, parse_qs
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import instaloader

# Global variables
COOKIE_GLOBAL = None
DRIVERS = {}
SESSION = None

# Rate limiting configuration
RATE_LIMIT_CONFIG = {
    'x': {
        'requests_per_minute': 50,  # Reduced from ~100
        'delay_between_requests': 1.2,  # Increased delay
        'batch_size': 25,  # Process in smaller batches
        'max_retries': 2
    },
    'instagram': {
        'requests_per_minute': 30,  # Reduced from unlimited
        'delay_between_requests': 2.5,  # Significant delay for Instagram
        'batch_size': 15,  # Very small batches for Instagram
        'max_retries': 3
    },
    'youtube': {
        'requests_per_minute': 100,  # YouTube has higher limits
        'delay_between_requests': 0.5,
        'batch_size': 50,
        'max_retries': 2
    },
    'tiktok': {
        'requests_per_minute': 40,
        'delay_between_requests': 1.5,
        'batch_size': 30,
        'max_retries': 2
    },
    'default': {
        'requests_per_minute': 60,
        'delay_between_requests': 1.0,
        'batch_size': 40,
        'max_retries': 2
    }
}

# Try imports for optional dependencies
try:
    from twscrape import API
    import nest_asyncio
    nest_asyncio.apply()
    TWSCRAPE_AVAILABLE = True
except ImportError:
    TWSCRAPE_AVAILABLE = False

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

class SocialMediaExtractor:
    def __init__(self):
        self.setup_credentials()
        self.request_timestamps = {
            'x': [],
            'instagram': [],
            'youtube': [],
            'tiktok': [],
            'stockbit': [],
            'linkedin': []
        }
    
    def run_sync(self, coro):
        """Run async function synchronously"""
        try:
            loop = asyncio.get_running_loop()
            return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    def rate_limit_delay(self, platform):
        """Implement rate limiting dengan exponential backoff"""
        config = RATE_LIMIT_CONFIG.get(platform, RATE_LIMIT_CONFIG['default'])
        
        # Clean old timestamps (older than 1 minute)
        now = time.time()
        self.request_timestamps[platform] = [
            ts for ts in self.request_timestamps[platform] 
            if now - ts < 60
        ]
        
        # Check if we're over the rate limit
        if len(self.request_timestamps[platform]) >= config['requests_per_minute']:
            sleep_time = 60 - (now - self.request_timestamps[platform][0]) + 1
            print(f"Rate limit reached for {platform}. Sleeping for {sleep_time:.1f} seconds...")
            time.sleep(sleep_time)
        
        # Add current timestamp
        self.request_timestamps[platform].append(now)
        
        # Apply delay between requests
        delay = config['delay_between_requests'] * (0.8 + 0.4 * random.random())  # Add jitter
        time.sleep(delay)
    
    def safe_api_call(self, platform, api_function, url, max_retries=None):
        """Wrapper untuk API calls dengan retry logic"""
        if max_retries is None:
            max_retries = RATE_LIMIT_CONFIG.get(platform, RATE_LIMIT_CONFIG['default'])['max_retries']
        
        for attempt in range(max_retries + 1):
            try:
                self.rate_limit_delay(platform)
                result = api_function(url)
                
                # Check for rate limit errors in response
                if (result.get('error') and 
                    any(keyword in result['error'].lower() for keyword in ['rate limit', 'too many requests', 'quota', 'limit exceeded'])):
                    if attempt < max_retries:
                        wait_time = (2 ** attempt) + random.random() * 2  # Exponential backoff with jitter
                        print(f"Rate limit detected for {platform}. Retry {attempt + 1}/{max_retries} in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                        continue
                
                return result
                
            except Exception as e:
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ['rate limit', 'too many requests', 'quota', 'limit exceeded']):
                    if attempt < max_retries:
                        wait_time = (2 ** attempt) + random.random() * 2
                        print(f"Rate limit exception for {platform}. Retry {attempt + 1}/{max_retries} in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        return {"url": url, "error": f"Rate limit exceeded after {max_retries} retries", "platform": platform}
                else:
                    # For other errors, don't retry
                    return {"url": url, "error": str(e), "platform": platform}
        
        return {"url": url, "error": f"Max retries ({max_retries}) exceeded", "platform": platform}

    def setup_credentials(self):
        """Setup credentials untuk semua platform - langsung setup tanpa prompt"""
        global COOKIE_GLOBAL, DRIVERS
        
        print("Setting up credentials for all platforms...")
        
        # ========== TIKTOK COOKIE SETUP ==========
        TIKTOK_COOKIE = (
            "delay_guest_mode_vid=5;msToken=WHtPOVvBrKwINoA7OCsBMEKYCTsEIPzKSnE21VHISMeJm5m3JNIsTKJeGfoqy_AipOsMPfQLwEIbT8uyWm8L1PL1WiJcD2ZsbHBiUgZWzGEYYBzVgbUZAW0Gt4y02hmN1dpxftVSfrCFduZj3F-6QhDl5I8=;"
            "tt_session_tlb_tag=sttt%7C2%7C_0ofyArOd-N5-B5eBnPvIf________-58pLu8QnB9S9q-aUGeuPygDIIsRbWMXpZV1E8tKJK4pc%3D;"
            "sid_guard=ff4a1fc80ace77e379f81e5e0673ef21%7C1764142344%7C15552000%7CMon%2C+25-May-2026+07%3A32%3A24+GMT;"
            "ttwid=1%7CMB4SFTX8wd9iapUFmHVatFfWUYqHDk-5mAle15FG-b0%7C1764219851%7C0feff73f72fc894d60523196e600bfe8252401e87085d8d0d78aa30299f5525e;"
            "perf_feed_cache={%22expireTimestamp%22:1764392400000%2C%22itemIds%22:[%227576601683778702613%22%2C%227566613695938186513%22%2C%227575572161658653972%22]};"
            "uid_tt=8920b53f3a19d0bd020ff406ef01446c9aa69f5467695b4d59979be7bae87165;"
            "passport_csrf_token_default=a33b443f9dc8766f1c85d2bdc3b7634b;"
            "s_v_web_id=verify_migyy51a_RoZVtrJf_DYdM_4ogl_BnF0_4BBd581BWcNX;"
            "_fbp=fb.1.1757916825275.1275385635;"
            "ssid_ucp_v1=1.0.1-KDBmNTA2NGJjY2U3YWU2MDA1NzYxOTRjYjkwZjc0NmUzMDc1YjM1OGMKGQiHiICMrOKN5GgQiNqayQYYsws4CEASSAQQAxoDbXkyIiBmZjRhMWZjODBhY2U3N2UzNzlmODFlNWUwNjczZWYyMTJOCiCYcrDBqBqqoD6Jbsy5a166u9Pbgx25nw42G5pb96hQLhIgrzXUMSQvCx5FlaOKD8QkSgPBz1uH1g6asJw7cA-rYW8YBCIGdGlrdG9r;"
            "tiktok_webapp_theme=light;"
            "_ttp=34jorasRTXKBh8DPFxPDu4PgJSQ;"
            "FPAU=1.2.186280606.1757916825;"
            "passport_csrf_token=a33b443f9dc8766f1c85d2bdc3b7634b;"
            "sessionid=ff4a1fc80ace77e379f81e5e0673ef21;"
            "sessionid_ss=ff4a1fc80ace77e379f81e5e0673ef21;"
            "sid_guard_ads=cdf71093876dff0f3ae0ed8321dcb7a2%7C1757916958%7C259200%7CThu%2C+18-Sep-2025+06%3A15%3A58+GMT;"
            "sid_tt=ff4a1fc80ace77e379f81e5e0673ef21;"
            "sid_ucp_v1=1.0.1-KDBmNTA2NGJjY2U3YWU2MDA1NzYxOTRjYjkwZjc0NmUzMDc1YjM1OGMKGQiHiICMrOKN5GgQiNqayQYYsws4CEASSAQQAxoDbXkyIiBmZjRhMWZjODBhY2U3N2UzNzlmODFlNWUwNjczZWYyMTJOCiCYcrDBqBqqoD6Jbsy5a166u9Pbgx25nw42G5pb96hQLhIgrzXUMSQvCx5FlaOKD8QkSgPBz1uH1g6asJw7cA-rYW8YBCIGdGlrdG9r;"
            "tiktok_webapp_theme_source=auto;"
            "tt_chain_token=k1XAmR5dA9FMMebuaqxf/g==;"
            "tt_csrf_token=dZXm05ve-6rqQy063P7bL7MIWojyaiB5LH1s;"
            "tta_attr_id_mirror=0.1757916818.7550195242662625297;"
            "uid_tt_ss=8920b53f3a19d0bd020ff406ef01446c9aa69f5467695b4d59979be7bae87165"
        )
        
        COOKIE_GLOBAL = TIKTOK_COOKIE
        print(f"TikTok cookie: ADA ({len(TIKTOK_COOKIE)} characters)")
        
        # X/Twitter Setup - AUTO SETUP
        if TWSCRAPE_AVAILABLE:
            try:
                AUTH_TOKEN = "ace24c753fc19383d5d986a43df31b29caba6b1c"
                CT0 = "ff91423e2459c60313e98b7ee8fa97aeb9b0ea66f53a0cf5c2932441013916d84c295af768d7a96baf3ea88a6a661e2a68d4dae3266ca37d42379e37e15996c8dec30bee0bcf4990e22aa776209f98ef"
                
                cookies_str = f"ct0={CT0}; auth_token={AUTH_TOKEN}"
                
                api = API()
                self.run_sync(api.pool.add_account("cookie_account", "", "", "", cookies=cookies_str))
                DRIVERS['x_api'] = api
                print("X/Twitter configured (auto tokens injected)")
            except Exception as e:
                print(f"X/Twitter setup failed: {e}")
        
        # YouTube Setup - AUTO SETUP
        try:
            API_KEY = "AIzaSyDnNlZRw-NIrvUlm72l6qjdReCdaHhc5kE"
            youtube = build("youtube", "v3", developerKey=API_KEY)
            DRIVERS['youtube_api'] = youtube
            print("YouTube configured")
        except Exception as e:
            print(f"YouTube setup failed: {e}")
        
        # Instagram Setup - tanpa login untuk deployment
        try:
            L = instaloader.Instaloader()
            DRIVERS['instagram_loader'] = L
            print("Instagram configured (public access only)")
        except Exception as e:
            print(f"Instagram setup failed: {e}")
        
        print("All credentials setup completed!")

    # ========== PLATFORM DETECTION ==========
    def detect_platform(self, url):
        url_lower = url.lower()
        if 'twitter.com' in url_lower or 'x.com' in url_lower:
            return 'x'
        elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
            return 'youtube'
        elif 'tiktok.com' in url_lower:
            return 'tiktok'
        elif 'stockbit.com' in url_lower:
            return 'stockbit'
        elif 'instagram.com' in url_lower:
            return 'instagram'
        elif 'linkedin.com' in url_lower:
            return 'linkedin'
        else:
            return 'unknown'

    # ========== X/TWITTER EXTRACTOR ==========
    TWEET_URL_RE = re.compile(r"(?:twitter|x)\.com/\w+/statuses?/(\d+)")

    def extract_tweet_id(self, url: str) -> str:
        m = self.TWEET_URL_RE.search(url)
        if not m:
            raise ValueError(f"Not a valid X/Twitter post URL: {url}")
        return m.group(1)   

   # def run_sync(self, coro):
    #    try:
    #       loop = asyncio.get_running_loop()
    #      return loop.run_until_complete(coro)
    # except RuntimeError:
    #    return asyncio.run(coro)

    def fetch_x_metrics(self, url: str):
        try:
            if 'x_api' not in DRIVERS:
                return {"error": "X/Twitter not configured"}
                
            tweet_id = int(self.extract_tweet_id(url))
            t = self.run_sync(DRIVERS['x_api'].tweet_details(tweet_id))
            if t is None:
                return {"error": "Tweet not returned"}

            rt = getattr(t, "retweetCount", None)
            qt = getattr(t, "quoteCount", None)
            if rt is None and qt is None:
                combined_repost = None
            else:
                combined_repost = (rt or 0) + (qt or 0)
            
            created_at = getattr(t, "date", None)
            date_str = None
            if created_at:
                try:
                    date_str = created_at.strftime("%b %d, %Y")
                except:
                    date_str = str(created_at)

            return {
                "date": date_str,
                "url": url,
                "author": getattr(t.user, "username", None),
                "content": getattr(t, "rawContent", "").replace("\n", " ").strip(),
                "followers": getattr(t.user, "followersCount", None),
                "views": getattr(t, "viewCount", None),
                "likes": getattr(t, "likeCount", None),
                "comments": getattr(t, "replyCount", None),
                "saves": getattr(t, "bookmarkCount", None),
                "shares": None,
                "reposts": combined_repost,
                "platform": "x"
            }
        except Exception as e:
            return {"url": url, "error": str(e), "platform": "x"}

    # ========== YOUTUBE EXTRACTOR ==========
    def extract_video_id(self, url: str) -> str:
        url = url.strip()
        if not url:
            raise ValueError("Empty URL")
        parsed = urlparse(url)
        if parsed.netloc in {"youtu.be"}:
            vid = parsed.path.lstrip("/")
            if vid:
                return vid
        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/")[2]
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            if "v" in qs and qs["v"]:
                return qs["v"][0]
        if parsed.path.startswith("/embed/"):
            return parsed.path.split("/")[2]
        last = parsed.path.rstrip("/").split("/")[-1]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", last):
            return last
        raise ValueError(f"Could not extract video ID from: {url}")

    def fetch_youtube_metrics(self, url: str):
        try:
            if 'youtube_api' not in DRIVERS:
                return {"error": "YouTube not configured"}
                
            video_id = self.extract_video_id(url)
            resp = DRIVERS['youtube_api'].videos().list(part="snippet,statistics", id=video_id).execute()
            
            if not resp.get("items"):
                return {"error": "Video not found"}
            
            item = resp["items"][0]
            snip = item.get("snippet", {})
            stats = item.get("statistics", {})
            
            channel_id = snip.get("channelId")
            channel_subs = None
            if channel_id:
                ch_resp = DRIVERS['youtube_api'].channels().list(part="statistics", id=channel_id).execute()
                if ch_resp.get("items"):
                    subs = ch_resp["items"][0].get("statistics", {}).get("subscriberCount")
                    channel_subs = int(subs) if subs else None
            
            published_at = snip.get("publishedAt")
            date_str = None
            if published_at:
                try:
                    dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    date_str = dt.strftime("%b %d, %Y")
                except:
                    date_str = published_at

            return {
                "date": date_str,
                "url": url,
                "author": snip.get("channelTitle"),
                "content": (snip.get("description") or "").replace("\n", " ").strip(),
                "followers": channel_subs,
                "views": int(stats.get("viewCount", 0)) if stats.get("viewCount") else None,
                "likes": int(stats.get("likeCount", 0)) if stats.get("likeCount") else None,
                "comments": int(stats.get("commentCount", 0)) if stats.get("commentCount") else None,
                "saves": None,
                "shares": None,
                "reposts": None,
                "platform": "youtube"
            }
        except Exception as e:
            return {"url": url, "error": str(e), "platform": "youtube"}

    # ========== TIKTOK EXTRACTOR ==========
    DEFAULT_HEADERS = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
    }

    # ---- Regex pattern ----
    SIGI_STATE_RE = re.compile(r'<script[^>]*id="SIGI_STATE"[^>]*>(.*?)</script>', re.DOTALL)
    NEXT_DATA_RE = re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
    UNIVERSAL_DATA_RE = re.compile(r'<script[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', re.DOTALL)

    def _parse_int(self, v: Any) -> Optional[int]:
        try:
            if v is None:
                return None
            if isinstance(v, (int, float)):
                return int(v)
            if isinstance(v, str):
                v = v.replace(",", "").strip()
                return int(v) if v.isdigit() else None
        except Exception:
            return None
        return None

    def _extract_hashtags(self, caption: Optional[str]) -> List[str]:
        if not caption or not isinstance(caption, str):
            return []
        pattern = r'#[\w\u00c0-\u024f\u1e00-\u1eff]+'
        seen, out = set(), []
        for tag in re.findall(pattern, caption, re.IGNORECASE):
            t = tag.lower()
            if t not in seen:
                seen.add(t)
                out.append(tag)
        return out

    def _ts_to_formatted(self, ts: Optional[int]) -> Optional[str]:
        """Konversi epoch ke format tanggal lokal (Asia/Jakarta)."""
        if not ts:
            return None
        try:
            dt = datetime.fromtimestamp(int(ts), tz=ZoneInfo("Asia/Jakarta")) if ZoneInfo else datetime.fromtimestamp(int(ts))
            return dt.strftime("%b %d, %Y")
        except Exception:
            return None

    def _extract_author(self, item: Dict[str, Any], sigi: Optional[Dict[str, Any]] = None):
        """Ambil username + followerCount dari itemStruct, fallback ke SIGI_STATE."""
        a = (item or {}).get("author") or {}
        astats = (item or {}).get("authorStats") or {}
        username = a.get("uniqueId")
        followers = self._parse_int(astats.get("followerCount"))

        if followers is None and sigi:
            try:
                um = (sigi.get("UserModule") or {})
                stats_by_user = um.get("stats") or {}
                if username and username in stats_by_user:
                    followers = self._parse_int(stats_by_user[username].get("followerCount"))
            except Exception:
                pass
        return username, followers

    # ---- Data class ----
    @dataclass
    class TikTokVideoStats:
        caption: Optional[str]
        views: Optional[int]
        likes: Optional[int]
        shares: Optional[int]
        comments: Optional[int]
        hashtags: Optional[List[str]]
        date_unix: Optional[int] = None
        date_str: Optional[str] = None
        author_username: Optional[str] = None
        author_followers: Optional[int] = None
        saves: Optional[int] = None

        def as_dict(self) -> Dict[str, Any]:
            return {
                "caption": self.caption,
                "views": self.views,
                "likes": self.likes,
                "shares": self.shares,
                "comments": self.comments,
                "hashtags": self.hashtags,
                "date_unix": self.date_unix,
                "date": self.date_str,
                "author_username": self.author_username,
                "author_followers": self.author_followers,
                "saves": self.saves,
            }

    # ---- Extractors ----
    def _extract_from_sigi_state(self, html: str) -> Optional[TikTokVideoStats]:
        m = self.SIGI_STATE_RE.search(html)
        if not m:
            return None
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        item_module = data.get("ItemModule") or {}
        if isinstance(item_module, dict) and item_module:
            first_item = next(iter(item_module.values()))
            if isinstance(first_item, dict):
                desc = first_item.get("desc")
                stats = first_item.get("stats") or {}
                ct_int = self._parse_int(first_item.get("createTime"))
                au, af = self._extract_author(first_item, data)
                return self.TikTokVideoStats(
                    caption=desc,
                    views=self._parse_int(stats.get("playCount")),
                    likes=self._parse_int(stats.get("diggCount")),
                    shares=self._parse_int(stats.get("shareCount")),
                    comments=self._parse_int(stats.get("commentCount")),
                    hashtags=self._extract_hashtags(desc),
                    date_unix=ct_int,
                    date_str=self._ts_to_formatted(ct_int),
                    author_username=au,
                    author_followers=af,
                    saves=self._parse_int(stats.get("collectCount")),
                )
        return None

    def _extract_from_universal_data(self, html: str) -> Optional[TikTokVideoStats]:
        m = self.UNIVERSAL_DATA_RE.search(html)
        if not m:
            return None
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        scopes_to_try = [
            ("__DEFAULT_SCOPE__", "webapp.video-detail"),
            ("__DEFAULT_SCOPE__", "webapp.photo-detail"),
        ]
        for scope_root, scope_key in scopes_to_try:
            try:
                item = (data.get(scope_root, {})
                            .get(scope_key, {})
                            .get("itemInfo", {})
                            .get("itemStruct", {}))
                if not isinstance(item, dict) or not item:
                    continue
                desc = item.get("desc")
                stats = item.get("stats", {}) or {}
                ct_int = self._parse_int(item.get("createTime"))
                au, af = self._extract_author(item)
                return self.TikTokVideoStats(
                    caption=desc,
                    views=self._parse_int(stats.get("playCount") or stats.get("playCountV2")),
                    likes=self._parse_int(stats.get("diggCount") or stats.get("diggCountV2")),
                    shares=self._parse_int(stats.get("shareCount")),
                    comments=self._parse_int(stats.get("commentCount")),
                    hashtags=self._extract_hashtags(desc),
                    date_unix=ct_int,
                    date_str=self._ts_to_formatted(ct_int),
                    author_username=au,
                    author_followers=af,
                    saves=self._parse_int(stats.get("collectCount")),
                )
            except Exception:
                continue
        return None

    def _extract_from_next_data(self, html: str) -> Optional[TikTokVideoStats]:
        m = self.NEXT_DATA_RE.search(html)
        if not m:
            return None
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        try:
            item = (data.get("props", {})
                    .get("pageProps", {})
                    .get("itemInfo", {})
                    .get("itemStruct", {}))
            if not isinstance(item, dict) or not item:
                return None
            desc = item.get("desc")
            stats = item.get("stats", {}) or {}
            ct_int = self._parse_int(item.get("createTime"))
            au, af = self._extract_author(item)
            return self.TikTokVideoStats(
                caption=desc,
                views=self._parse_int(stats.get("playCount")),
                likes=self._parse_int(stats.get("diggCount")),
                shares=self._parse_int(stats.get("shareCount")),
                comments=self._parse_int(stats.get("commentCount")),
                hashtags=self._extract_hashtags(desc),
                date_unix=ct_int,
                date_str=self._ts_to_formatted(ct_int),
                author_username=au,
                author_followers=af,
                saves=self._parse_int(stats.get("collectCount")),
            )
        except Exception:
            return None

    def scrape_tiktok_video(self, url: str, cookie: Optional[str] = None, timeout: int = 15):
        """Ambil metadata TikTok (caption, views, likes, shares, saves, dst)."""
        url = url.replace("m.tiktok.com/", "www.tiktok.com/")
        if "/photo/" in url and "/video/" not in url:
            url = url.replace("/photo/", "/video/")
        session = requests.Session()
        headers = self.DEFAULT_HEADERS.copy()
        if cookie:
            headers["Cookie"] = cookie
        resp = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            resp.raise_for_status()
        html = resp.text
        for extractor in (self._extract_from_universal_data, self._extract_from_sigi_state, self._extract_from_next_data):
            stats = extractor(html)
            if stats:
                return stats
        raise RuntimeError("Parsing gagal. Halaman mungkin diblokir geo, private, atau perlu Cookie.")

    def fetch_tiktok_metrics(self, url: str):
        try:
            stats = self.scrape_tiktok_video(url, cookie=COOKIE_GLOBAL)
            return {
                "date": stats.date_str,
                "url": url,
                "author": stats.author_username,
                "content": (stats.caption or "").replace("\n", " ").strip(),
                "followers": stats.author_followers,
                "views": stats.views,
                "likes": stats.likes,
                "comments": stats.comments,
                "saves": stats.saves,
                "shares": stats.shares,
                "reposts": None,
                "platform": "tiktok"
            }
        except Exception as e:
            return {"url": url, "error": str(e), "platform": "tiktok"}

    # ========== STOCKBIT EXTRACTOR ==========
    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        driver = webdriver.Chrome(options=chrome_options)
        return driver

    def extract_stockbit_data(self, driver, link):
        try:
            driver.get(link)
            
            wait = WebDriverWait(driver, 10)
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-cy="post-guest-footer"], .post-guest-footer, [class*="like"], [class*="comment"]')))
            except:
                pass
            
            driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(2)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            data = {
                'url': link,
                'date': 'N/A',
                'author': 'N/A',
                'content': 'N/A',
                'followers': 0,
                'likes': 0,
                'comments': 0
            }
            
            # Extract engagement
            data.update(self.extract_engagement(soup))
            
            # Extract author dan followers
            author_data = self.extract_author_info(driver, soup, link)
            data.update(author_data)
            
            # Extract content dan date
            content_data = self.extract_content_and_date(soup)
            data.update(content_data)
            
            return data
            
        except Exception as e:
            return {
                'url': link,
                'date': 'Error',
                'author': 'Error',
                'content': 'Error',
                'followers': 0,
                'likes': 0,
                'comments': 0
            }

    def extract_engagement(self, soup):
        data = {'likes': 0, 'comments': 0}
        
        footer = soup.find('div', {'data-cy': 'post-guest-footer'})
        if footer:
            # Extract likes
            likes_elem = footer.find('a', class_=lambda x: x and 'post-guest-footer-likes' in x)
            if likes_elem:
                like_text = likes_elem.get_text(strip=True)
                numbers = re.findall(r'\d+', like_text)
                if numbers:
                    data['likes'] = int(numbers[0])
                else:
                    all_text = ' '.join(likes_elem.find_all(text=True, recursive=True))
                    numbers = re.findall(r'\d+', all_text)
                    if numbers:
                        data['likes'] = int(numbers[0])
            
            # Extract comments
            comments_elem = footer.find('a', class_=lambda x: x and 'post-guest-footer-replies' in x)
            if comments_elem:
                comment_text = comments_elem.get_text(strip=True)
                numbers = re.findall(r'\d+', comment_text)
                if numbers:
                    data['comments'] = int(numbers[0])
        
        return data

    def extract_author_info(self, driver, soup, link):
        data = {'author': 'N/A', 'followers': 0}
        
        try:
            # Extract username dari title
            title = soup.find('title')
            if title:
                title_text = title.get_text()
                username_match = re.search(r'([^()]+?)\s*\(?([^()]+)\)?\s*on\s*Stockbit', title_text)
                if username_match:
                    if username_match.group(2):
                        data['author'] = username_match.group(2).strip()
                    else:
                        data['author'] = username_match.group(1).strip()
            
            # Jika berhasil dapat username, extract followers
            if data['author'] != 'N/A':
                followers = self.extract_followers_from_profile(driver, data['author'])
                data['followers'] = followers
                
                # Kembali ke post asli
                driver.get(link)
                time.sleep(1)
        
        except Exception as e:
            pass
        
        return data

    def extract_followers_from_profile(self, driver, username):
        try:
            profile_url = f"https://stockbit.com/{username}?source="
            original_window = driver.current_window_handle
            
            # Buka profile di tab baru
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[1])
            driver.get(profile_url)
            time.sleep(3)
            
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(1)
            
            profile_soup = BeautifulSoup(driver.page_source, 'html.parser')
            followers = 0
            
            # Cari followers dengan berbagai method
            all_text = profile_soup.get_text()
            patterns = [
                r'(\d+)\s*Followers',
                r'Followers\s*(\d+)',
                r'(\d+)\s*Pengikut',
                r'Pengikut\s*(\d+)'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, all_text, re.IGNORECASE)
                if matches:
                    followers = int(matches[0])
                    break
            
            # Tutup tab profile
            driver.close()
            driver.switch_to.window(original_window)
            
            return followers
            
        except:
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                driver.switch_to.window(driver.window_handles[0])
            except:
                pass
            return 0

    def extract_content_and_date(self, soup):
        data = {'content': 'N/A', 'date': 'N/A'}
        
        # Extract content dari meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            content = meta_desc.get('content', '')
            content_clean = re.sub(r'\s+', ' ', content).strip()
            data['content'] = content_clean
        
        # Extract date
        time_elem = soup.find('time')
        if time_elem:
            datetime_attr = time_elem.get('datetime')
            if datetime_attr:
                data['date'] = datetime_attr
            else:
                data['date'] = time_elem.get_text(strip=True)
        
        return data

    def fetch_stockbit_metrics(self, url: str):
        try:
            driver = self.setup_driver()
            data = self.extract_stockbit_data(driver, url)
            driver.quit()
            
            return {
                "date": data['date'],
                "url": url,
                "author": data['author'],
                "content": data['content'],
                "followers": data['followers'],
                "views": None,
                "likes": data['likes'],
                "comments": data['comments'],
                "saves": None,
                "shares": None,
                "reposts": None,
                "platform": "stockbit"
            }
        except Exception as e:
            return {"url": url, "error": str(e), "platform": "stockbit"}
            
    # ========== INSTAGRAM EXTRACTOR ==========
    INSTAGRAM_RE = re.compile(r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)")

    def extract_shortcode(self, url: str) -> str:
        m = self.INSTAGRAM_RE.search(url)
        if not m:
            raise ValueError(f"Not a valid Instagram post URL: {url}")
        return m.group(1)

    def fetch_instagram_metrics(self, url: str):
        try:
            if 'instagram_loader' not in DRIVERS:
                return {"error": "Instagram not configured"}
                
            shortcode = self.extract_shortcode(url)
            post = instaloader.Post.from_shortcode(DRIVERS['instagram_loader'].context, shortcode)
            owner = post.owner_profile
            
            taken_at = post.date_utc
            date_str = None
            if taken_at:
                try:
                    date_str = taken_at.strftime("%b %d, %Y")
                except:
                    date_str = str(taken_at)

            return {
                "date": date_str,
                "url": url,
                "author": post.owner_username,
                "content": (post.caption or "").replace("\n", " ").strip(),
                "followers": owner.followers,
                "views": post.video_view_count if post.is_video else None,
                "likes": post.likes,
                "comments": post.comments,
                "saves": None,
                "shares": None,
                "reposts": None,
                "platform": "instagram"
            }
        except Exception as e:
            return {"url": url, "error": str(e), "platform": "instagram"}

    # ========== LINKEDIN EXTRACTOR ==========
    def parse_linkedin_followers(self, text: str) -> Optional[int]:
        """Convert '2,799 followers' or '22K followers' to int."""
        if not text:
            return None
        text = text.lower().strip().replace("followers", "").strip()
        try:
            if "k" in text:
                return int(float(text.replace("k", "").replace(",", "")) * 1000)
            elif "m" in text:
                return int(float(text.replace("m", "").replace(",", "")) * 1_000_000)
            else:
                return int(text.replace(",", ""))
        except Exception:
            return None

    def fetch_linkedin_metrics(self, url: str):
        try:
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            driver = webdriver.Chrome(options=options)

            driver.get(url)
            time.sleep(5)

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            # Username
            author = None
            name_tag = soup.select_one("a.text-sm.link-styled")
            if name_tag:
                author = name_tag.get_text(strip=True)

            # Likes
            likes = 0
            likes_tag = soup.find("a", attrs={"data-test-id": "social-actions__reactions"})
            if likes_tag:
                likes = int(likes_tag.get("data-num-reactions", "0"))

            # Comments
            comments = 0
            comments_tag = soup.find("a", attrs={"data-test-id": "social-actions__comments"})
            if comments_tag:
                comments = int(comments_tag.get("data-num-comments", "0"))

            # Followers (on post page)
            followers = None
            follow_tag = soup.find("p", string=re.compile(r"followers", re.I))
            if follow_tag:
                followers = self.parse_linkedin_followers(follow_tag.text)
            
            # Content
            content = None
            content_tag = soup.find("p", attrs={"data-test-id": "main-feed-activity-card__commentary"})
            if content_tag:
                content = content_tag.get_text(" ", strip=True)
                content = re.sub(r'\s+', ' ', content) 
                content = content.strip() 

            # Jika followers masih None, buka profil user
            if not followers and name_tag and name_tag.get("href"):
                profile_url = name_tag["href"]
                if not profile_url.startswith("http"):
                    profile_url = "https://www.linkedin.com" + profile_url
                driver.get(profile_url)
                time.sleep(5)
                profile_html = driver.page_source
                profile_soup = BeautifulSoup(profile_html, "html.parser")
                span = profile_soup.find("span", string=re.compile(r"followers", re.I))
                if span:
                    followers = self.parse_linkedin_followers(span.text)

            driver.quit()

            return {
                "date": None,
                "url": url,
                "author": author,
                "content": content,
                "followers": followers,
                "views": None,
                "likes": likes,
                "comments": comments,
                "saves": None,
                "shares": None,
                "reposts": None,
                "platform": "linkedin"
            }
            
        except Exception as e:
            try:
                driver.quit()
            except:
                pass
            return {"url": url, "error": str(e), "platform": "linkedin"}

    def print_progress_bar(self, current, total, bar_length=50):
        percent = float(current) * 100 / total
        arrow = '█' * int(percent/100 * bar_length)
        spaces = ' ' * (bar_length - len(arrow))
        
        if current == total:
            print(f'\rProgress: [{arrow}{spaces}] {current}/{total} ({percent:.1f}%) - Completed!')
        else:
            print(f'\rProgress: [{arrow}{spaces}] {current}/{total} ({percent:.1f}%)', end='', flush=True)

    def process_links(self, links: List[str]):
        """Process multiple links and return results"""
        if not links:
            return {"error": "No links provided"}
        
        print(f"Detected {len(links)} total links")
        
        # Group links by platform for batch processing
        platform_groups = {}
        for link in links:
            platform = self.detect_platform(link)
            if platform not in platform_groups:
                platform_groups[platform] = []
            platform_groups[platform].append(link)
        
        print("Platform breakdown:")
        for platform, platform_links in platform_groups.items():
            if platform_links:
                print(f"   {platform.upper():<10}: {len(platform_links)}")
        
        # Process all links
        print("Processing all links with rate limiting...")
        all_results = []
        
        # Platform processors dengan safe wrapper
        processors = {
            'x': lambda url: self.safe_api_call('x', self.fetch_x_metrics, url),
            'youtube': lambda url: self.safe_api_call('youtube', self.fetch_youtube_metrics, url), 
            'tiktok': lambda url: self.safe_api_call('tiktok', self.fetch_tiktok_metrics, url),
            'stockbit': lambda url: self.safe_api_call('stockbit', self.fetch_stockbit_metrics, url),
            'instagram': lambda url: self.safe_api_call('instagram', self.fetch_instagram_metrics, url),
            'linkedin': lambda url: self.safe_api_call('linkedin', self.fetch_linkedin_metrics, url)
        }
        
        total_links = len(links)
        processed_count = 0
        
        # Show initial progress
        self.print_progress_bar(0, total_links)
        
        # Process links in original order but with platform-specific rate limiting
        for url in links:
            platform = self.detect_platform(url)
            
            if platform in processors:
                result = processors[platform](url)
            else:
                result = {
                    "date": None, "url": url, "author": None, "content": None,
                    "followers": None, "views": None, "likes": None, "comments": None,
                    "saves": None, "shares": None, "reposts": None, "platform": "unknown",
                    "error": "Unsupported platform"
                }
            
            all_results.append(result)
            processed_count += 1
            self.print_progress_bar(processed_count, total_links)
        
        print()  # New line after progress bar
        
        # Create DataFrame - maintain original order
        df = pd.DataFrame(all_results)
        
        # Ensure standard column order
        standard_columns = ["date", "url", "author", "content", "followers", "views", 
                        "likes", "comments", "saves", "shares", "reposts", "platform", "error"]
        
        # Add missing columns with None values
        for col in standard_columns:
            if col not in df.columns:
                df[col] = None
        
        # Reorder columns
        df = df[standard_columns]
        
        # Convert DataFrame to list of dictionaries for JSON response
        results_data = df.to_dict('records')
        
        # Add summary statistics
        platform_stats = df['platform'].value_counts().to_dict()
        error_stats = {}
        for platform in platform_stats.keys():
            error_count = df[df['platform'] == platform]['error'].notna().sum()
            error_stats[platform] = {
                'total': platform_stats[platform],
                'success': platform_stats[platform] - error_count,
                'errors': error_count
            }
        
        return {
            "results": results_data,
            "summary": {
                "total_processed": len(df),
                "platform_stats": error_stats,
                "rate_limiting_applied": True
            }
        }