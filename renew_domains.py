import os
import sys
import json
import time
import hmac
import base64
import hashlib
import traceback
from datetime import datetime

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 兼容 Windows 控制台默认 GBK 编码，避免 emoji 打印时报错
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ============================================================
# DNSHE 多账号域名自动续期脚本（飞书通知版）
# 运行环境：GitHub Actions，工作流见 .github/workflows/renew.yml
#
# 配置来源（优先级：环境变量 > 本地 .env 文件）：
#   DNSHE_API_KEY_1 ~ 10        DNSHE 各账号 API Key
#   DNSHE_API_SECRET_1 ~ 10     DNSHE 各账号 API Secret
#   FEISHU_WEBHOOK_URL          飞书群机器人 Webhook 地址
#   FEISHU_SIGN_SECRET          飞书签名校验密钥（可选，未配置则不带签名）
#   MANUAL_RUN                  手动触发时为 true，运行后会发送一条链路确认消息
# ============================================================

BASE_URL = "https://api005.dnshe.com/index.php?m=domain_hub"

# 续期阈值：到期时间小于该天数则执行续期
RENEW_THRESHOLD_DAYS = 180

# 最多支持的 DNSHE 账号数量
MAX_ACCOUNTS = 10

# 账号之间的处理间隔（秒），避免触发 API 速率限制
ACCOUNT_SLEEP_SECONDS = 2

# 请求重试次数（指数退避 time.sleep(2 ** i)）
RETRY_TIMES = 3

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LAST_RENEW_PATH = os.path.join(SCRIPT_DIR, "last_renew.json")


def _get_bool_env(name, default):
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} 必须是 true/false")


FEISHU_WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
FEISHU_SIGN_SECRET = os.environ.get("FEISHU_SIGN_SECRET", "").strip() or None
MANUAL_RUN = _get_bool_env("MANUAL_RUN", False)


def _collect_accounts():
    """从环境变量收集全部 DNSHE 账号（DNSHE_API_KEY_N / DNSHE_API_SECRET_N，N 从 1 开始）"""
    accounts = []
    for index in range(1, MAX_ACCOUNTS + 1):
        key = os.environ.get(f"DNSHE_API_KEY_{index}")
        secret = os.environ.get(f"DNSHE_API_SECRET_{index}")
        if not key and not secret:
            continue
        if not key or not secret:
            print(f"警告: 账号{index} 缺少 API Key 或 API Secret，已跳过")
            continue
        accounts.append({"name": f"账号{index}", "key": key, "secret": secret})
    return accounts


def send_feishu(text):
    """发送飞书文本消息；未配置 webhook 或发送失败时打印并返回 False"""
    if not FEISHU_WEBHOOK_URL:
        print("[飞书] 未配置 FEISHU_WEBHOOK_URL，跳过通知")
        return False

    payload = {"msg_type": "text", "content": {"text": text}}

    if FEISHU_SIGN_SECRET:
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{FEISHU_SIGN_SECRET}"
        sign = base64.b64encode(
            hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        ).decode("utf-8")
        payload["timestamp"] = timestamp
        payload["sign"] = sign

    try:
        resp = requests.post(FEISHU_WEBHOOK_URL, json=payload, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        if body.get("code", 0) != 0:
            print(f"[飞书] 发送失败: {body.get('msg') or body}")
            return False
        return True
    except Exception as e:
        print(f"[飞书] 发送异常: {e}")
        return False


def request_with_retry(method, url, **kwargs):
    """带重试的请求：对超时/连接错误/HTTP 5xx 指数退避重试，全失败后抛异常"""
    timeout = kwargs.pop("timeout", 30)
    last_error = None
    for attempt in range(RETRY_TIMES):
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code >= 500:
                last_error = RuntimeError(f"HTTP {resp.status_code}")
                time.sleep(2 ** attempt)
                continue
            return resp
        except (requests.Timeout, requests.ConnectionError) as e:
            last_error = e
            if attempt < RETRY_TIMES - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"请求失败（已重试 {RETRY_TIMES} 次）: {last_error}")


def api_get(url, headers):
    resp = request_with_retry("GET", url, headers=headers)
    try:
        return resp.json()
    except ValueError as e:
        raise RuntimeError(f"响应不是合法 JSON: {e}")


def api_post(url, headers, payload):
    resp = request_with_retry("POST", url, headers=headers, json=payload)
    try:
        return resp.json()
    except ValueError as e:
        raise RuntimeError(f"响应不是合法 JSON: {e}")


def _headers(account):
    return {
        "X-API-Key": account["key"],
        "X-API-Secret": account["secret"],
        "Content-Type": "application/json",
    }


def _list_url():
    return (
        f"{BASE_URL}&endpoint=subdomains&action=list"
        "&fields=id,subdomain,rootdomain,full_domain,status,expires_at,never_expires"
    )


def _renew_url():
    return f"{BASE_URL}&endpoint=subdomains&action=renew"


def _parse_expires(value):
    """解析到期时间，支持 'YYYY-MM-DD HH:MM:SS' 与 'YYYY-MM-DD' 两种格式"""
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"到期时间格式无法解析: {value!r}")


def preflight(accounts):
    """运行前预检：账号认证、域名列表获取、到期时间字段解析。
    任一账号预检失败则发送飞书通知并返回 None（不做任何续期）。"""
    results = []
    for account in accounts:
        try:
            data = api_get(_list_url(), _headers(account))
            if not data.get("success", False):
                raise RuntimeError(data.get("message") or data.get("msg") or str(data))
            subdomains = data.get("subdomains", [])
            if not isinstance(subdomains, list):
                raise RuntimeError(f"subdomains 字段异常: {type(subdomains)}")
            for domain in subdomains:
                if "id" not in domain or "full_domain" not in domain:
                    raise RuntimeError(f"域名字段缺失: {domain}")
                if domain.get("expires_at"):
                    _parse_expires(domain["expires_at"])
            results.append({"account": account, "subdomains": subdomains})
            print(f"✅ 预检通过：{account['name']}（{len(subdomains)} 个域名）")
        except Exception as e:
            message = f"❌ DNSHE 预检失败：{account['name']}，错误：{e}"
            print(message)
            send_feishu(message)
            return None
    return results


def _load_last_renew():
    try:
        with open(LAST_RENEW_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_last_renew(data):
    try:
        with open(LAST_RENEW_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("[状态] last_renew.json 已更新")
    except OSError as e:
        print(f"[状态] 写入 last_renew.json 失败: {e}")


def _last_renew_text(ts):
    if not ts:
        return "从未续期"
    try:
        past = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        days = (datetime.now() - past).days
        if days <= 0:
            return "今天已续期"
        return f"{days} 天前"
    except ValueError:
        return "记录时间格式异常"


def _run():
    accounts = _collect_accounts()
    if not accounts:
        message = (
            "⚠️ 未检测到任何 DNSHE 账号配置，"
            "请在 GitHub Secrets 或本地 .env 中配置 DNSHE_API_KEY_1 / DNSHE_API_SECRET_1"
        )
        print(message)
        send_feishu(message)
        return 1

    today = datetime.now()
    last_renew = _load_last_renew()
    current_domains = set()

    # 预检：任一账号失败即通知并退出，不做续期
    preflight_results = preflight(accounts)
    if preflight_results is None:
        return 1

    if MANUAL_RUN:
        total_domains = sum(len(entry["subdomains"]) for entry in preflight_results)
        send_feishu(
            f"ℹ️ 手动触发运行：DNSHE 预检通过（{len(accounts)} 个账号，"
            f"{total_domains} 个域名），飞书通知链路正常。"
        )

    any_renewed = False
    any_error = False

    for index, entry in enumerate(preflight_results):
        account = entry["account"]
        if index > 0:
            time.sleep(ACCOUNT_SLEEP_SECONDS)

        print(f"========== {account['name']} ==========")
        for domain in entry["subdomains"]:
            full_domain = domain.get("full_domain", "")
            current_domains.add(full_domain)
            domain_id = domain.get("id")
            expires_at_str = domain.get("expires_at")
            never_expires = domain.get("never_expires", 0)

            if never_expires:
                print(f"⏭️ {full_domain}: 已设置为永不过期，跳过续期")
                continue

            days_left = None
            if expires_at_str:
                days_left = (_parse_expires(expires_at_str) - today).days

            if days_left is not None:
                print(f"ℹ️ {full_domain}: 剩余 {days_left} 天")
                if days_left >= RENEW_THRESHOLD_DAYS:
                    continue

            ago = _last_renew_text(last_renew.get(full_domain))

            try:
                result = api_post(_renew_url(), _headers(account), {"subdomain_id": domain_id})
                if result.get("success"):
                    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    last_renew[full_domain] = now
                    new_expiry = result.get("new_expires_at", "未知")
                    charged = result.get("charged_amount", 0)
                    send_feishu(
                        f"✅ DNSHE 续期成功：{full_domain}"
                        f"（剩余 {days_left} 天 → 已续期，新到期 {new_expiry}，"
                        f"消耗 {charged} 积分，上次续期 {ago}）"
                    )
                    any_renewed = True
                else:
                    msg = result.get("message") or result.get("msg") or str(result)
                    send_feishu(f"❌ DNSHE 续期失败：{full_domain}，错误：{msg}")
                    any_error = True
            except Exception as e:
                send_feishu(f"❌ DNSHE 续期失败：{full_domain}，错误：{e}")
                any_error = True

    # 清理已不在域名列表中的旧记录并保存
    for stale in set(last_renew) - current_domains:
        del last_renew[stale]
    _save_last_renew(last_renew)

    if not any_renewed and not any_error:
        print("所有域名剩余天数均充足（或为永不过期），本次无需续期。")
    return 0


def main():
    try:
        return _run()
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        send_feishu(f"❌ DNSHE 脚本异常，请查看 GitHub Actions 日志。\n{tb}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
