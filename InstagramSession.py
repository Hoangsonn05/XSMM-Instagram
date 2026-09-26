# ig_job.py
import os
import re
import sys
import json
import time
import random
import logging
import requests
from datetime import datetime
from colorama import init, Fore, Style

init(autoreset=True)


class C:
    R  = Fore.LIGHTRED_EX
    G  = Fore.LIGHTGREEN_EX
    Y  = Fore.LIGHTYELLOW_EX
    B  = Fore.LIGHTBLUE_EX
    M  = Fore.LIGHTMAGENTA_EX
    Cy = Fore.LIGHTCYAN_EX
    W  = Fore.LIGHTWHITE_EX
    K  = Fore.LIGHTBLACK_EX
    RS = Style.RESET_ALL
    BR = Style.BRIGHT


def cprint(text, color=""):
    print(f"{color}{text}{C.RS}")


PREFIX = "[XSMM-TOOL] "


class Spinner:
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message=""):
        self.message = message
        self._start = 0
        self._i = 0

    def _render(self, elapsed, i, end=False):
        mm, ss = divmod(int(elapsed), 60)
        if end:
            frame = f"{C.G}✓{C.RS}"
            tail = f" {C.G}— xong{C.RS}"
        else:
            frame = f"{C.Y}{self.FRAMES[i % len(self.FRAMES)]}{C.RS}"
            tail = ""
        line = (f"{C.M}{PREFIX}{C.RS}"
                f"{frame} "
                f"{C.K}[{mm:02d}:{ss:02d}]{C.RS} "
                f"{self.message}{tail}")
        sys.stdout.write("\r\033[K" + line)
        sys.stdout.flush()

    def __enter__(self):
        self._start = time.time()
        self._i = 0
        self._render(0, 0)
        return self

    def __exit__(self, *args):
        elapsed = time.time() - self._start
        self._render(elapsed, self._i, end=True)
        print()

    def tick(self):
        elapsed = time.time() - self._start
        self._render(elapsed, self._i)
        self._i += 1


def spin_wait(seconds, message="chờ", block=0.08):
    start = time.time()
    i = 0
    while True:
        elapsed = time.time() - start
        if elapsed >= seconds:
            break
        mm, ss = divmod(int(elapsed), 60)
        frame = Spinner.FRAMES[i % len(Spinner.FRAMES)]
        remain = seconds - elapsed
        line = (f"{C.M}{PREFIX}{C.RS}"
                f"{C.Y}{frame}{C.RS} "
                f"{C.K}[{mm:02d}:{ss:02d}]{C.RS} "
                f"{message} {C.K}(còn {remain:.1f}s){C.RS}")
        sys.stdout.write("\r\033[K" + line)
        sys.stdout.flush()
        time.sleep(block)
        i += 1
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()


def countdown_wait(seconds, message="Nghỉ chu kỳ"):
    start = time.time()
    last = None
    while True:
        remain = seconds - (time.time() - start)
        if remain <= 0:
            break
        mm, ss = divmod(int(remain), 60)
        line = (f"{C.M}{PREFIX}{C.RS}"
                f"{C.Y}⏸{C.RS} "
                f"{C.K}[{mm:02d}:{ss:02d}]{C.RS} "
                f"{C.W}{message}{C.RS}, "
                f"{C.Cy}còn {int(remain)}s...{C.RS}")
        if line != last:
            sys.stdout.write("\r\033[K" + line)
            sys.stdout.flush()
            last = line
        time.sleep(0.05)
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()


class ColorFormatter(logging.Formatter):
    def format(self, record):
        ts = f"{C.K}{self.formatTime(record, '%H:%M:%S')}{C.RS}"
        msg = record.getMessage()
        if "✓" in msg:
            msg = f"{C.G}{msg}{C.RS}"
        elif "✗" in msg or "lỗi" in msg.lower():
            msg = f"{C.R}{msg}{C.RS}"
        elif "⚠" in msg:
            msg = f"{C.Y}{msg}{C.RS}"
        return f"[{ts}] {msg}"


log = logging.getLogger("igjob")
log.setLevel(logging.INFO)
_h = logging.StreamHandler()
_h.setFormatter(ColorFormatter())
log.addHandler(_h)


# ====================================================================== #
class InstagramAPI:
    BASE = "https://www.instagram.com"
    APP_ID = "936619743392459"

    DOC_LIKE = ("usePolarisLikeMediaXIGLikeMutation", "27182485238052618")
    DOC_UNLIKE = ("usePolarisUnlikeMediaXIGUnlikeMutation", "27182485238052619")
    DOC_FOLLOW = ("usePolarisFollowUserFollowMutation", "27767812149509802")

    def __init__(self, cookie_str: str, timeout: int = 15):
        self.timeout = timeout
        self.cookies = self._parse_cookie(cookie_str)
        self.session_id = self.cookies.get("sessionid")
        self.csrf_token = self.cookies.get("csrftoken")
        self.ds_user_id = self.cookies.get("ds_user_id")
        if not self.session_id:
            raise ValueError("Cookie thiếu 'sessionid'")
        if not self.ds_user_id:
            raise ValueError("Cookie thiếu 'ds_user_id'")

        self.fb_dtsg = None
        self.lsd = None
        self.jazoest = None
        self.rev = None
        self.hs = None

        # trạng thái sau load()
        self.alive = False
        self.suspended = False
        self.load_error = None

        self.session = self._build_session()

    @staticmethod
    def _parse_cookie(cookie_str: str) -> dict:
        out = {}
        for part in cookie_str.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
        return out

    def _build_session(self) -> requests.Session:
        s = requests.Session()
        for k, v in self.cookies.items():
            s.cookies.set(k, v, domain=".instagram.com")
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8,vi;q=0.7",
            "X-CSRFToken": self.csrf_token or "",
            "X-IG-App-ID": self.APP_ID,
            "X-ASBD-ID": "129477",
            "X-IG-WWW-Claim": "0",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.BASE}/",
            "Origin": self.BASE,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
        })
        return s

    # ------------------------------------------------------------------ #
    #  LOAD + CHECK SESSION QUA HTML TOKEN
    # ------------------------------------------------------------------ #
    def load(self) -> bool:
        """
        GET instagram.com/ rồi soi HTML.
        Trả về True nếu session còn live, False nếu die/suspended.
        Cập nhật: self.alive, self.suspended, self.load_error
        """
        self.alive = False
        self.suspended = False
        self.load_error = None

        try:
            r = self.session.get(self.BASE, timeout=self.timeout,
                                 allow_redirects=True)
        except Exception as e:
            self.load_error = f"request EXC: {e}"
            return False

        # 1. check suspended trước (URL hoặc header)
        final_url = (r.url or "").lower()
        loc = (r.headers.get("Location") or "").lower()
        if "suspended" in final_url or "suspended" in loc:
            self.suspended = True
            self.load_error = "account suspended"
            return False

        html = r.text or ""
        low = html.lower()

        # 2. redirect về login / challenge
        if "/accounts/login" in final_url or "/challenge/" in final_url:
            self.load_error = f"redirect: {final_url}"
            return False

        # 3. trang HTML có chữ suspended / disabled
        if "your account has been suspended" in low \
           or "account has been disabled" in low \
           or '"userstatus":"suspended"' in low:
            self.suspended = True
            self.load_error = "html suspended"
            return False

        # 4. thử lấy token từ HTML
        self._extract_tokens(html)

        # 5. check "viewerId" khớp ds_user_id → chắc chắn live
        m = re.search(r'"viewerId"\s*:\s*"(\d+)"', html)
        if m:
            if m.group(1) == str(self.ds_user_id):
                self.alive = True
                return True
            else:
                self.load_error = f"viewerId mismatch ({m.group(1)})"
                return False

        # 6. fallback: HTML có "viewer":{...} + csrf_token → vẫn coi live
        if '"viewer":{' in html and self.csrf_token:
            self.alive = True
            return True

        # 7. fallback cuối: có csrf_token lấy từ HTML + có fb_dtsg → live
        if self.fb_dtsg and self.lsd:
            self.alive = True
            return True

        self.load_error = "không tìm thấy token session trong HTML"
        return False

    def _extract_tokens(self, html: str):
        m = re.findall(r'"DTSGInitialData",\[\],\{"token":"([^"]+)"\}', html)
        if m:
            self.fb_dtsg = m[-1]
        m = re.findall(r'"LSD",\[\],\{"token":"([^"]+)"\}', html)
        if m:
            self.lsd = m[-1]
        m = re.search(r'"InstagramSecurityConfig",\[\],\{"csrf_token":"([^"]+)"\}', html)
        if m:
            self.csrf_token = m.group(1)
            self.session.headers["X-CSRFToken"] = self.csrf_token
        m = re.search(r'"__spin_r":(\d+)', html)
        if m:
            self.rev = m.group(1)
        m = re.search(r'"haste_session":"([^"]+)"', html)
        if m:
            self.hs = m.group(1)
        m = re.search(r'jazoest=(\d+)', html)
        if m:
            self.jazoest = m.group(1)
        elif self.fb_dtsg:
            self.jazoest = "2" + str(sum(ord(c) for c in self.fb_dtsg))

    # ------------------------------------------------------------------ #
    def is_alive(self) -> bool:
        return self.alive

    def is_suspended(self) -> bool:
        return self.suspended

    def request(self, method, path, **kw):
        url = path if path.startswith("http") else f"{self.BASE}{path}"
        kw.setdefault("timeout", self.timeout)
        return self.session.request(method, url, **kw)

    def get(self, path, **kw):  return self.request("GET", path, **kw)
    def post(self, path, **kw): return self.request("POST", path, **kw)

    def graphql(self, friendly_name, doc_id, variables):
        if not (self.fb_dtsg and self.lsd):
            raise RuntimeError("Chưa load() để lấy token.")
        data = {
            "av": self.ds_user_id,
            "__d": "www", "__user": "0", "__a": "1", "__req": "1",
            "__hs": self.hs or "20718.HYP:instagram_web_pkg.2.1...0",
            "dpr": "1", "__ccg": "EXCELLENT",
            "__rev": self.rev or "1048131409",
            "__s": "abc:def:ghi", "__hsi": "0", "__comet_req": "7",
            "fb_dtsg": self.fb_dtsg,
            "jazoest": self.jazoest or "",
            "lsd": self.lsd,
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": friendly_name,
            "server_timestamps": "true",
            "variables": json.dumps(variables),
            "doc_id": doc_id,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-FB-Friendly-Name": friendly_name,
            "X-CSRFToken": self.csrf_token,
            "X-IG-App-ID": self.APP_ID,
            "X-FB-LSD": self.lsd,
            "Origin": self.BASE,
            "Referer": f"{self.BASE}/",
        }
        return self.session.post(f"{self.BASE}/api/graphql",
                                 data=data, headers=headers,
                                 timeout=self.timeout)

    def _post_graphql(self, friendly, doc, variables):
        try:
            r = self.graphql(friendly, doc, variables)
        except Exception:
            return None
        if r.status_code != 200:
            return None
        try:
            return r.json()
        except Exception:
            return None

    def me(self):
        """
        Lấy username từ HTML trang chủ (không dùng API info nữa).
        """
        try:
            r = self.session.get(f"{self.BASE}/{self.ds_user_id}/",
                                 timeout=self.timeout,
                                 allow_redirects=True)
        except Exception:
            return None
        if r.status_code != 200:
            return None
        html = r.text or ""
        m = re.search(r'"username"\s*:\s*"([^"]+)"', html)
        uname = m.group(1) if m else None
        if not uname:
            # thử meta og:title
            m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            if m:
                uname = m.group(1).split(" ")[0].lstrip("@")
        if not uname:
            return None
        return {
            "username": uname,
            "full_name": None,
            "pk": self.ds_user_id,
            "follower_count": None,
            "following_count": None,
        }

    @staticmethod
    def _pk(media_id: str) -> str:
        return media_id.split("_")[0]

    def like(self, media_id: str) -> bool:
        pk = self._pk(media_id)
        inp = {
            "actor_id": self.ds_user_id,
            "client_mutation_id": "1",
            "container_module": "feed_timeline",
            "media_id": pk,
        }
        friendly, doc = self.DOC_LIKE
        data = self._post_graphql(friendly, doc, {"input": inp})
        if not data:
            return False
        try:
            return data["data"]["xig_media_like"]["media"]["has_liked"]
        except (KeyError, TypeError):
            return False

    def unlike(self, media_id: str) -> bool:
        pk = self._pk(media_id)
        inp = {
            "actor_id": self.ds_user_id,
            "client_mutation_id": "1",
            "container_module": "feed_timeline",
            "media_id": pk,
        }
        friendly, doc = self.DOC_UNLIKE
        data = self._post_graphql(friendly, doc, {"input": inp})
        if not data:
            return False
        try:
            return not data["data"]["xig_media_unlike"]["media"]["has_liked"]
        except (KeyError, TypeError):
            return False

    def follow(self, user_id: str) -> bool:
        friendly, doc = self.DOC_FOLLOW
        data = self._post_graphql(friendly, doc, {"target_user_id": str(user_id)})
        if not data:
            return False
        try:
            return data["data"]["xdt_create_friendship"]["friendship_status"]["following"]
        except (KeyError, TypeError):
            return False


# ====================================================================== #
class XsmmClient:
    BASE = "https://xsmm.net"

    def __init__(self, token: str, timeout: int = 20, debug: bool = False):
        self.timeout = timeout
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        })

    def _req(self, method, path, **kw):
        kw.setdefault("timeout", self.timeout)
        url = f"{self.BASE}{path}"
        try:
            r = self.session.request(method, url, **kw)
        except Exception as e:
            if self.debug:
                print(f"  {C.R}[DEBUG] {method} {path} EXC: {e}{C.RS}")
            return 0, {"error": str(e)}
        if self.debug:
            print(f"  {C.K}[DEBUG] {method} {path} → {r.status_code}{C.RS}")
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"error": r.text[:300]}

    def user(self):
        code, data = self._req("GET", "/api/taskapi/user")
        if code == 200:
            return data.get("user")
        return None

    def balance(self) -> int:
        u = self.user()
        return u.get("points", 0) if u else 0

    def accounts(self, page=1, limit=100, account_type=None, search=None):
        params = {"page": page, "limit": limit}
        if account_type:
            params["account_type"] = account_type
        if search:
            params["search"] = search
        code, data = self._req("GET", "/api/taskapi/accounts", params=params)
        if code == 200:
            return data.get("accounts", [])
        return []

    def active_account(self):
        code, data = self._req("GET", "/api/taskapi/accounts/active")
        if code == 200 and isinstance(data, dict):
            return data
        return None

    def add_account(self, acc_type, link_account, active=False):
        payload = {"type": acc_type, "link_account": link_account}
        if active:
            payload["active"] = True
        code, data = self._req("POST", "/api/taskapi/accounts", json=payload)
        if code not in (200, 201):
            err = data.get("error") if isinstance(data, dict) else None
            return None, err or f"HTTP {code}"
        return data, None

    def set_active(self, xsmm_id):
        code, data = self._req("PUT",
                               f"/api/taskapi/accounts/{xsmm_id}/set-active")
        if code not in (200, 201):
            err = data.get("error") if isinstance(data, dict) else None
            return None, err or f"HTTP {code}"
        return data, None

    def get_tasks(self, task_type, typejob="normal,better,best"):
        params = {"type": task_type, "typejob": typejob}
        code, data = self._req("GET", "/api/taskapi/tasks", params=params)
        if code != 200:
            return []
        if isinstance(data, dict) and "error" in data:
            if self.debug:
                print(f"  {C.R}[DEBUG] tasks error: {data}{C.RS}")
            return []
        return data if isinstance(data, list) else []

    def complete(self, task_type, task_ids, cookie=None):
        payload = {"type": task_type, "task_id": task_ids}
        if cookie:
            payload["cookie_check"] = cookie
        code, data = self._req("POST", "/api/taskapi/tasks/complete", json=payload)
        if code != 200:
            return None
        return data


# ====================================================================== #
class Config:
    def __init__(self, path="config.json"):
        self.path = path
        self.xsmm_token = ""
        self.debug = False
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    d = json.load(f)
                self.xsmm_token = d.get("xsmm_token", "")
                self.debug = bool(d.get("debug", False))
            except Exception as e:
                log.warning(f"Config load lỗi: {e}")

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"xsmm_token": self.xsmm_token, "debug": self.debug},
                      f, indent=2)


class AccountStore:
    def __init__(self, path="accounts.json"):
        self.path = path
        self.accounts = []
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    self.accounts = json.load(f)
            except Exception as e:
                log.warning(f"Accounts load lỗi: {e}")
                self.accounts = []

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.accounts, f, ensure_ascii=False, indent=2)

    @staticmethod
    def parse_cookie(cookie_str):
        out = {}
        for part in cookie_str.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
        return out

    def find(self, ds_user_id):
        for a in self.accounts:
            if a["ds_user_id"] == ds_user_id:
                return a
        return None

    def add(self, cookie_str, username="", xsmm_id=""):
        cookie_str = cookie_str.strip()
        ck = self.parse_cookie(cookie_str)
        ds_user_id = ck.get("ds_user_id")
        if not ds_user_id:
            raise ValueError("Cookie không có 'ds_user_id' (id)")
        if self.find(ds_user_id):
            raise ValueError(f"Tài khoản {ds_user_id} đã tồn tại")

        acc = {
            "ds_user_id": ds_user_id,
            "cookie": cookie_str,
            "username": username,
            "xsmm_id": xsmm_id,
            "enabled": True,
            "fail_count": 0,
            "added_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.accounts.append(acc)
        self.save()
        return acc

    def remove(self, ds_user_id):
        before = len(self.accounts)
        self.accounts = [a for a in self.accounts if a["ds_user_id"] != ds_user_id]
        if len(self.accounts) < before:
            self.save()
            return True
        return False

    def clear(self):
        self.accounts = []
        self.save()

    def toggle(self, ds_user_id):
        a = self.find(ds_user_id)
        if a:
            a["enabled"] = not a.get("enabled", True)
            self.save()
        return a

    def enabled(self):
        return [a for a in self.accounts if a.get("enabled", True)]


# ====================================================================== #
class IGTaskWorker:
    MAX_FAIL = 3   # fail 3 lần liên tiếp mới tắt acc

    def __init__(self, xsmm, store,
                 min_delay=2.0, max_delay=5.0,
                 jobs_per_cycle=0, cycle_sleep=60,
                 batch_size=15, empty_sleep=10,
                 follow_cache_min=8, follow_cache_max=12):
        self.xsmm = xsmm
        self.store = store
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.jobs_per_cycle = jobs_per_cycle
        self.cycle_sleep = cycle_sleep
        self.batch_size = batch_size
        self.empty_sleep = empty_sleep
        self.follow_cache_min = follow_cache_min
        self.follow_cache_max = follow_cache_max

        self.ig_cache = {}
        self.cycle_count = {}

        self.total_done = 0
        self.total_fail = 0
        self.total_points = 0
        self.balance = 0

    def _mark_fail(self, acc, reason=""):
        acc["fail_count"] = acc.get("fail_count", 0) + 1
        if acc["fail_count"] >= self.MAX_FAIL:
            acc["enabled"] = False
            self.store.save()
            cprint(f"  ⚠ {acc.get('username') or acc['ds_user_id']}: "
                   f"fail {acc['fail_count']} lần — tự động TẮT ({reason})", C.Y)

    def _mark_ok(self, acc):
        if acc.get("fail_count", 0) != 0:
            acc["fail_count"] = 0
            self.store.save()

    def _get_ig(self, acc):
        uid = acc["ds_user_id"]
        if uid in self.ig_cache:
            return self.ig_cache[uid]

        with Spinner(f"Đang load session cho {uid}...") as sp:
            try:
                ig = InstagramAPI(acc["cookie"])
                sp.tick()
                ok = ig.load()
                sp.tick()
                if not ok:
                    reason = ig.load_error or "load fail"
                    if ig.is_suspended():
                        cprint(f"  ⚠ {uid}: SUSPENDED — tự động TẮT", C.R)
                        acc["enabled"] = False
                        self.store.save()
                        return None
                    cprint(f"  ⚠ {uid}: {reason}", C.Y)
                    self._mark_fail(acc, reason)
                    return None
                sp.tick()
                me = ig.me()
                if me:
                    acc["username"] = me.get("username", "")
                    self._mark_ok(acc)
                self.ig_cache[uid] = ig
                return ig
            except Exception as e:
                cprint(f"  ⚠ {uid}: init lỗi: {e}", C.Y)
                self._mark_fail(acc, str(e))
                return None

    def _ensure_xsmm_id(self, acc, ig):
        if acc.get("xsmm_id"):
            return acc["xsmm_id"]
        accs = self.xsmm.accounts(limit=200, account_type="instagram")
        uname = (acc.get("username") or "").lower()
        for x in accs:
            name = str(x.get("name") or "").lower()
            if name == uname:
                acc["xsmm_id"] = str(x.get("id") or "")
                self.store.save()
                return acc["xsmm_id"]
        return None

    def _do_action(self, ig, task_type, task):
        target = task.get("target_id")
        if not target:
            return False
        if task_type == "instagram_like":
            return ig.like(target)
        if task_type == "instagram_follow":
            return ig.follow(target)
        return False

    def _log_success(self, label, task_type, task_id, points, num, bal):
        print(
            f"{C.K}[{num:>4}]{C.RS} "
            f"{C.Cy}{label}{C.RS} "
            f"{C.K}==>{C.RS} "
            f"{C.M}{task_type}{C.RS} "
            f"{C.K}==>{C.RS} "
            f"{C.W}{task_id}{C.RS} "
            f"{C.K}==>{C.RS} "
            f"{C.G}+{points} xu{C.RS} "
            f"{C.K}==>{C.RS} "
            f"{C.Y}{bal} xu{C.RS}"
        )

    def _complete_batch(self, task_type, items, label, cookie=None):
        if not items:
            return 0

        task_ids = [t[0] for t in items]
        balance_before = self.balance

        res = self.xsmm.complete(task_type, task_ids, cookie=cookie)

        if res and res.get("points", 0) > 0:
            self.balance = self.xsmm.balance()

        if not res:
            return 0

        pts = res.get("points", 0)
        if pts > 0:
            self.total_points += pts
            per = pts // len(task_ids) if task_ids else 0
            for i, (tid, dnum) in enumerate(items):
                bal_show = balance_before + per * (i + 1)
                self._log_success(label, task_type, tid, per, dnum, bal_show)
        else:
            print(f"  {C.Y}⚠ points=0{C.RS} "
                  f"{C.K}|{C.RS} {res.get('message', '')}")

        cd = res.get("countdown")
        if cd:
            countdown_wait(cd, "server countdown")

        if res.get("retry"):
            print(f"  {C.Y}⚠ retry=true{C.RS}")
        return pts

    # ------------------------------------------------------------------ #
    def _check_live_accounts(self):
        enabled = self.store.enabled()
        if not enabled:
            return

        print(f"\n{C.B}{'─'*60}{C.RS}")
        print(f"{C.Cy}▸ CHECK LIVE {len(enabled)} account...{C.RS}")
        print(f"{C.B}{'─'*60}{C.RS}")

        dead = []
        for acc in enabled:
            uid = acc["ds_user_id"]
            uname = acc.get("username") or "?"

            try:
                ig = InstagramAPI(acc["cookie"])
                ok = ig.load()
            except Exception as e:
                print(f"  {C.R}✗ {uname} — {e} (tắt){C.RS}")
                acc["enabled"] = False
                self.store.save()
                dead.append(uname)
                continue

            if ig.is_suspended():
                print(f"  {C.R}✗ {uname} — SUSPENDED (tự động TẮT){C.RS}")
                acc["enabled"] = False
                self.store.save()
                dead.append(uname)
                continue

            if not ok:
                self._mark_fail(acc, ig.load_error or "")
                print(f"  {C.Y}✗ {uname} — {ig.load_error} "
                      f"(fail {acc['fail_count']}/{self.MAX_FAIL}){C.RS}")
            else:
                self._mark_ok(acc)
                self.ig_cache[uid] = ig
                print(f"  {C.G}✓ {uname} — live{C.RS}")

        if dead:
            print(f"\n  {C.R}Đã tắt {len(dead)} account: "
                  f"{', '.join(dead)}{C.RS}")

    # ------------------------------------------------------------------ #
    def _work_account(self, acc, task_type):
        uid = acc["ds_user_id"]
        uname = acc.get("username") or "?"
        cookie = acc["cookie"]
        ig = self._get_ig(acc)
        if ig is None:
            return 0, 0

        xsmm_id = self._ensure_xsmm_id(acc, ig)
        if not xsmm_id:
            print(f"  {C.R}✗ {uname}: không tìm thấy trên xsmm{C.RS}")
            return 0, 0

        _, err = self.xsmm.set_active(xsmm_id)
        if err:
            print(f"  {C.R}✗ set-active lỗi: {err}{C.RS}")
            return 0, 0

        tasks = self.xsmm.get_tasks(task_type)
        if not tasks:
            return 0, 0

        tasks.sort(key=lambda t: t.get("points", 0), reverse=True)
        tasks = tasks[: self.batch_size]

        is_follow = (task_type == "instagram_follow")
        follow_buffer = []
        follow_target = random.randint(self.follow_cache_min, self.follow_cache_max) \
            if is_follow else 0

        done_ids = []
        for t in tasks:
            tid = t.get("id")
            try:
                ok = self._do_action(ig, task_type, t)
            except Exception:
                ok = False

            if ok:
                done_ids.append(tid)
                self.total_done += 1
                dnum = self.total_done
                self.cycle_count[uid] = self.cycle_count.get(uid, 0) + 1

                if not is_follow:
                    self._complete_batch(task_type, [(tid, dnum)],
                                         uname, cookie=cookie)
                else:
                    follow_buffer.append((tid, dnum))
                    if len(follow_buffer) >= follow_target:
                        self._complete_batch(task_type, follow_buffer,
                                             uname, cookie=cookie)
                        follow_buffer = []
                        follow_target = random.randint(
                            self.follow_cache_min, self.follow_cache_max
                        )
            else:
                self.total_fail += 1

            delay = random.uniform(self.min_delay, self.max_delay)
            spin_wait(delay, f"chờ {delay:.1f}s")

            if self.jobs_per_cycle and self.cycle_count.get(uid, 0) >= self.jobs_per_cycle:
                countdown_wait(
                    self.cycle_sleep,
                    f"Nghỉ chu kỳ {uname} sau {self.cycle_count[uid]} job",
                )
                self.cycle_count[uid] = 0

        if is_follow and follow_buffer:
            self._complete_batch(task_type, follow_buffer, uname, cookie=cookie)

        return len(done_ids), len(tasks)

    def run(self, task_types, total_jobs=0):
        if isinstance(task_types, str):
            task_types = [task_types]

        enabled = self.store.enabled()
        if not enabled:
            cprint("Không có tài khoản nào được bật!", C.R)
            return

        self.balance = self.xsmm.balance()

        print()
        cprint("═" * 60, C.B)
        cprint(f"  🚀 BẮT ĐẦU: {len(enabled)} account | "
               f"jobs={', '.join(task_types)} | "
               f"balance={self.balance} xu", C.Cy + C.BR)
        cprint("═" * 60, C.B)

        try:
            while True:
                if total_jobs and self.total_done >= total_jobs:
                    break

                round_has_work = False
                for acc in self.store.enabled():
                    if total_jobs and self.total_done >= total_jobs:
                        break
                    for tt in task_types:
                        if total_jobs and self.total_done >= total_jobs:
                            break
                        try:
                            done, total = self._work_account(acc, tt)
                            if total > 0:
                                round_has_work = True
                        except KeyboardInterrupt:
                            raise
                        except Exception as e:
                            cprint(f"Account {acc['ds_user_id']} lỗi: {e}", C.R)

                self._check_live_accounts()

                if not round_has_work:
                    print()
                    countdown_wait(self.empty_sleep,
                                   "không có task, chờ round tiếp")

        except KeyboardInterrupt:
            print()
            cprint("⏹  Ctrl+C — dừng.", C.Y)
        finally:
            if total_jobs and self.total_done >= total_jobs:
                cprint(f"\n🎯 Đã đạt {self.total_done}/{total_jobs} job.",
                       C.G + C.BR)
            self._summary()

    def _summary(self):
        print()
        cprint("═" * 60, C.B)
        cprint("  📊 TỔNG KẾT", C.Cy + C.BR)
        cprint(f"    ✓ done    : {self.total_done}", C.G)
        cprint(f"    ✗ fail    : {self.total_fail}", C.R)
        cprint(f"    ★ points  : {self.total_points} xu", C.Y)
        cprint(f"    💰 balance : {self.balance} xu", C.M)
        cprint("═" * 60, C.B)


# ====================================================================== #
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def ask(prompt, default=None, cast=str):
    s = input(f"{C.Cy}{prompt}{C.RS}").strip()
    if not s and default is not None:
        return default
    try:
        return cast(s)
    except Exception:
        return default


def pause():
    input(f"\n{C.K}Nhấn Enter để tiếp tục...{C.RS}")


def header(title):
    print()
    print(f"{C.B}{'═'*60}{C.RS}")
    print(f"{C.Cy}{C.BR}  {title}{C.RS}")
    print(f"{C.B}{'═'*60}{C.RS}")


def menu_item(num, label, color=C.W):
    print(f"  {C.M}{num}{C.RS}. {color}{label}{C.RS}")


def list_accounts(store):
    if not store.accounts:
        cprint("\n(chưa có tài khoản nào)", C.K)
        return
    print()
    print(f"{C.K}{'USERNAME':<18} {'DS_ID':<14} {'XSMM_ID':<26} {'ST':<4}{C.RS}")
    print(f"{C.K}{'─'*68}{C.RS}")
    for a in store.accounts:
        st = f"{C.G}B{C.RS}" if a.get("enabled", True) else f"{C.R}T{C.RS}"
        u = a.get("username") or "(?)"
        print(f"{C.Cy}{u:<18}{C.RS} "
              f"{C.W}{a['ds_user_id']:<14}{C.RS} "
              f"{C.Y}{a.get('xsmm_id') or '?':<26}{C.RS} "
              f"{st}")


def add_account(store, config):
    header("THÊM TÀI KHOẢN IG")
    cprint("Paste cookie string (bắt buộc có ds_user_id):", C.Y)
    cookie = input(f"{C.Cy}> {C.RS}").strip()
    if not cookie:
        cprint("Hủy.", C.K); return

    try:
        with Spinner("Đang load IG session...") as sp:
            ig = InstagramAPI(cookie)
            ok = ig.load()
            sp.tick()
            if ig.is_suspended():
                cprint("✗ Account bị SUSPENDED", C.R); return
            if not ok:
                cprint(f"✗ Session die: {ig.load_error}", C.R); return
            me = ig.me()
            sp.tick()
        if not me or not me.get("username"):
            cprint("✗ Không lấy được username", C.R); return
        username = me["username"]
        cprint(f"✓ IG: {C.W}{username}{C.RS} (id={me['pk']})", C.G)
    except Exception as e:
        cprint(f"✗ Lỗi: {e}", C.R); return

    xsmm_id = ""
    if config.xsmm_token:
        try:
            with Spinner(f"Đang add {username} lên XSMM (active)...") as sp:
                xsmm = XsmmClient(config.xsmm_token, debug=config.debug)
                res, err = xsmm.add_account(
                    "instagram",
                    f"https://www.instagram.com/{username}/",
                    active=True,
                )
                sp.tick()
            if err:
                cprint(f"⚠ Add XSMM lỗi: {err}", C.Y)
            else:
                cprint(f"✓ Đã add lên XSMM (active)", C.G)
                if res:
                    xsmm_id = str(res.get("id") or "")
                    cprint(f"  xsmm_id = {C.Y}{xsmm_id}{C.RS}")
        except Exception as e:
            cprint(f"⚠ XSMM exception: {e}", C.Y)

    try:
        acc = store.add(cookie, username=username, xsmm_id=xsmm_id)
        cprint(f"✓ Đã thêm tài khoản {acc['ds_user_id']}", C.G)
    except Exception as e:
        cprint(f"✗ Lỗi: {e}", C.R)


def toggle_account(store):
    list_accounts(store)
    key = input(f"\n{C.Cy}Nhập username / ds_id: {C.RS}").strip()
    a = None
    for x in store.accounts:
        if x.get("username") == key or x["ds_user_id"] == key:
            a = x; break
    if a:
        a["enabled"] = not a.get("enabled", True)
        if a["enabled"]:
            a["fail_count"] = 0
        store.save()
        status = f"{C.G}BẬT{C.RS}" if a['enabled'] else f"{C.R}TẮT{C.RS}"
        cprint(f"✓ {a.get('username') or a['ds_user_id']} → {status}", C.G)
    else:
        cprint("✗ Không tìm thấy", C.R)


def remove_account(store):
    list_accounts(store)
    key = input(f"\n{C.Cy}Nhập username / ds_id: {C.RS}").strip()
    target = None
    for x in store.accounts:
        if x.get("username") == key or x["ds_user_id"] == key:
            target = x; break
    if target and store.remove(target["ds_user_id"]):
        cprint(f"✓ Đã xóa {target.get('username') or target['ds_user_id']}", C.G)
    else:
        cprint("✗ Không tìm thấy", C.R)


def refresh_xsmm_ids(config, store):
    header("REFRESH XSMM_ID CHO TẤT CẢ ACCOUNT")
    if not config.xsmm_token:
        cprint("⚠ Chưa có token", C.Y); return
    xsmm = XsmmClient(config.xsmm_token, debug=config.debug)
    accs = xsmm.accounts(limit=200, account_type="instagram")

    by_name = {}
    for x in accs:
        name = str(x.get("name") or "").lower()
        if name:
            by_name[name] = str(x.get("id") or "")

    for a in store.accounts:
        uname = (a.get("username") or "").lower()
        if not uname:
            cprint(f"  ⚠ {a['ds_user_id']}: chưa có username", C.Y); continue
        if uname in by_name:
            a["xsmm_id"] = by_name[uname]
            store.save()
            cprint(f"  ✓ {uname} → xsmm_id={by_name[uname]}", C.G)
        else:
            cprint(f"  ✗ {uname}: không có trên xsmm", C.R)


def check_xsmm_accounts(config, store):
    header("TÀI KHOẢN TRÊN XSMM")
    if not config.xsmm_token:
        cprint("⚠ Chưa có token", C.Y); return
    xsmm = XsmmClient(config.xsmm_token, debug=config.debug)

    print(f"\n{C.Cy}--- Active account ---{C.RS}")
    act = xsmm.active_account()
    if act:
        for k, v in act.items():
            print(f"  {C.K}{k:16}{C.RS} = {C.W}{v}{C.RS}")
    else:
        cprint("  (không có active)", C.K)

    print(f"\n{C.Cy}--- Tất cả account ---{C.RS}")
    accs = xsmm.accounts(limit=100, account_type="instagram")
    for i, a in enumerate(accs, 1):
        print(f"{C.M}[{i}]{C.RS} "
              f"id={C.W}{a.get('id')}{C.RS} | "
              f"name={C.Cy}{a.get('name')}{C.RS} | "
              f"active={C.Y}{a.get('is_active')}{C.RS}")


def account_menu(store, config):
    while True:
        clear_screen()
        header("QUẢN LÝ TÀI KHOẢN")
        tok = config.xsmm_token
        tok_show = (tok[:25] + "...") if len(tok) > 25 else (tok or "(chưa có)")
        dbg = f"{C.G}ON{C.RS}" if config.debug else f"{C.K}OFF{C.RS}"
        print(f"  {C.K}XSMM Token :{C.RS} {C.Y}{tok_show}{C.RS}")
        print(f"  {C.K}Debug mode :{C.RS} {dbg}")
        print(f"  {C.K}IG accounts:{C.RS} "
              f"{C.G}{len(store.enabled())} bật{C.RS} / "
              f"{C.W}{len(store.accounts)} tổng{C.RS}")
        print(f"{C.K}{'─'*60}{C.RS}")
        menu_item(1, "Xem danh sách IG account")
        menu_item(2, "Thêm IG account (paste cookie)", C.G)
        menu_item(3, "Bật / tắt IG account")
        menu_item(4, "Xóa 1 IG account", C.R)
        menu_item(5, "Xóa HẾT IG account", C.R)
        menu_item(6, "Chỉnh sửa token XSMM", C.Y)
        menu_item(7, "Refresh xsmm_id cho tất cả account", C.Cy)
        menu_item(8, "Check account trên XSMM", C.Cy)
        menu_item(9, "Bật/tắt debug mode", C.Cy)
        menu_item(0, "Quay lại", C.K)
        print(f"{C.B}{'═'*60}{C.RS}")

        c = input(f"{C.Cy}Chọn: {C.RS}").strip()

        if c == "0":
            return
        elif c == "1":
            list_accounts(store); pause()
        elif c == "2":
            add_account(store, config); pause()
        elif c == "3":
            toggle_account(store); pause()
        elif c == "4":
            remove_account(store); pause()
        elif c == "5":
            ans = input(f"{C.R}Xóa HẾT? (yes/no): {C.RS}").strip().lower()
            if ans == "yes":
                store.clear(); cprint("✓ Đã xóa hết.", C.G)
            pause()
        elif c == "6":
            t = input(f"{C.Cy}Nhập XSMM token mới: {C.RS}").strip()
            if t:
                config.xsmm_token = t; config.save()
                cprint("✓ Đã lưu.", C.G)
            pause()
        elif c == "7":
            refresh_xsmm_ids(config, store); pause()
        elif c == "8":
            check_xsmm_accounts(config, store); pause()
        elif c == "9":
            config.debug = not config.debug; config.save()
            cprint(f"✓ Debug = {'ON' if config.debug else 'OFF'}", C.G)
            pause()
        else:
            cprint("Không hợp lệ.", C.R); pause()


def choose_task_types():
    clear_screen()
    header("CHỌN LOẠI JOB (chọn nhiều, cách nhau dấu phẩy)")
    menu_item(1, "Instagram Like  (complete từng job)", C.G)
    menu_item(2, "Instagram Follow (gộp cache 8-12)", C.Cy)
    menu_item(0, "Quay lại", C.K)
    print(f"{C.B}{'═'*60}{C.RS}")
    cprint("Ví dụ: 1,2  →  chạy cả Like và Follow", C.K)
    m = {"1": "instagram_like", "2": "instagram_follow"}
    while True:
        c = input(f"{C.Cy}Chọn: {C.RS}").strip()
        if c == "0" or not c:
            return None
        parts = [p.strip() for p in c.split(",") if p.strip()]
        if all(p in m for p in parts):
            types = [m[p] for p in parts]
            cprint(f"→ {', '.join(types)}", C.G)
            return types
        cprint("Không hợp lệ.", C.R)


def config_run():
    header("CẤU HÌNH CHẠY")
    total = ask("Số job muốn chạy (0 = vô hạn): ", default=0, cast=int)
    min_d = ask("Delay tối thiểu mỗi job (giây) [2]: ", default=2.0, cast=float)
    max_d = ask("Delay tối đa mỗi job (giây) [5]: ", default=5.0, cast=float)
    per_cycle = ask("Nghỉ sau bao nhiêu job (0 = không nghỉ) [0]: ",
                    default=0, cast=int)
    cycle_sleep = 0
    if per_cycle > 0:
        cycle_sleep = ask("Thời gian nghỉ (giây) [60]: ", default=60, cast=int)
    empty_sleep = ask("Nghỉ khi hết task (giây) [10]: ", default=10, cast=int)

    fc_min = ask("Cache follow - min [8]: ", default=8, cast=int)
    fc_max = ask("Cache follow - max [12]: ", default=12, cast=int)
    if fc_max < fc_min:
        fc_max = fc_min

    print()
    return {
        "total_jobs": total, "min_delay": min_d, "max_delay": max_d,
        "jobs_per_cycle": per_cycle, "cycle_sleep": cycle_sleep,
        "empty_sleep": empty_sleep,
        "follow_cache_min": fc_min, "follow_cache_max": fc_max,
    }


def main_menu():
    config = Config()
    store = AccountStore()

    while True:
        clear_screen()
        print()
        cprint("╔" + "═" * 58 + "╗", C.M + C.BR)
        cprint("║" + "  🤖  IG JOB AUTO TOOL".center(58) + "║", C.Cy + C.BR)
        cprint("╚" + "═" * 58 + "╝", C.M + C.BR)
        print()
        on  = len(store.enabled())
        tot = len(store.accounts)
        acc_color = C.G if on > 0 else C.R
        print(f"  {C.K}IG accounts:{C.RS} {acc_color}{on} bật{C.RS} "
              f"{C.K}/{C.RS} {C.W}{tot} tổng{C.RS}")
        tok_ok = f"{C.G}✓ có{C.RS}" if config.xsmm_token else f"{C.R}✗ chưa có{C.RS}"
        print(f"  {C.K}XSMM token :{C.RS} {tok_ok}")
        print(f"{C.K}{'─'*60}{C.RS}")
        menu_item(1, "▶  Chạy job", C.G + C.BR)
        menu_item(2, "⚙  Quản lý tài khoản", C.Cy)
        menu_item(0, "✕  Thoát", C.K)
        print(f"{C.M}{'═'*60}{C.RS}")

        c = input(f"{C.Cy}Chọn: {C.RS}").strip()

        if c == "0":
            cprint("Bye 👋", C.M)
            return
        elif c == "2":
            account_menu(store, config)
        elif c == "1":
            if not config.xsmm_token:
                cprint("⚠ Chưa có XSMM token.", C.Y); pause(); continue
            if not store.enabled():
                cprint("⚠ Không có IG account nào được bật.", C.Y); pause(); continue

            task_types = choose_task_types()
            if not task_types:
                continue
            cfg = config_run()

            xsmm = XsmmClient(config.xsmm_token, debug=config.debug)
            worker = IGTaskWorker(
                xsmm, store,
                min_delay=cfg["min_delay"],
                max_delay=cfg["max_delay"],
                jobs_per_cycle=cfg["jobs_per_cycle"],
                cycle_sleep=cfg["cycle_sleep"],
                empty_sleep=cfg["empty_sleep"],
                follow_cache_min=cfg["follow_cache_min"],
                follow_cache_max=cfg["follow_cache_max"],
            )
            worker.run(task_types, total_jobs=cfg["total_jobs"])
            pause()
        else:
            cprint("Không hợp lệ.", C.R); pause()


if __name__ == "__main__":
    main_menu()