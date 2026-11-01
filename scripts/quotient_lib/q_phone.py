"""1.3.3: the installment notices on the phone too (Francesco, 01/11/2026: "oltre ad avere le notifiche sul pc
come già avviene puoi riceverle anche sul telefono"). Three ways, each off until it is set up:

- Telegram: a bot of your own (from @BotFather) sends you the notice. Its token is a secret: Quotient reads it
  from an environment variable or from a file of yours, never from config.json, and never prints it.
- ntfy (https://ntfy.sh): a free app, no account; the notice goes to a topic name only you know.
- webhook: any address that takes a POST (Discord and Slack "incoming webhooks", Home Assistant, n8n, ...).
  The address is a secret too, so it is read like the Telegram token.

Other apps (WhatsApp, Signal, Matrix, Pushover, ...) are not built in yet: CONTRIBUTING.md says how to add one.
Best effort: a failed send never stops an installment; `phone test` shows what went wrong."""
import json
import os
import urllib.parse
import urllib.request

from quotient_lib import q_settings

TIMEOUT = 20


def secret(conf, key):
    """A secret from the environment variable or the file named in the config (never from the config itself)."""
    name = conf.get(key + "_env")
    if name and os.environ.get(name):
        return os.environ[name].strip()
    path = conf.get(key + "_file")
    if path:
        path = os.path.expanduser(path)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
    return ""


def post(url, data=None, body=None, headers=None):
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers or {}, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.status


def send_telegram(conf, title, body, link):
    token = secret(conf, "token")
    if not token or not conf.get("chat_id"):
        return None
    data = {"chat_id": conf["chat_id"], "text": "%s\n%s" % (title, body), "disable_web_page_preview": "true"}
    if conf.get("thread_id"):
        data["message_thread_id"] = conf["thread_id"]
    return post("https://api.telegram.org/bot%s/sendMessage" % token, data=data)


def send_ntfy(conf, title, body, link):
    topic = conf.get("topic") or secret(conf, "topic")
    if not topic:
        return None
    server = (conf.get("server") or "https://ntfy.sh").rstrip("/")
    # The title goes in the JSON body, not in a header, so any language's letters arrive as they are.
    msg = {"topic": topic, "title": title, "message": body}
    return post(server, body=json.dumps(msg).encode("utf-8"), headers={"Content-Type": "application/json"})


def send_webhook(conf, title, body, link):
    url = secret(conf, "url")
    if not url:
        return None
    kind = conf.get("kind") or "json"
    text = "%s\n%s" % (title, body)
    msg = ({"content": text[:1900]} if kind == "discord" else {"text": text} if kind == "slack" else
           {"title": title, "message": body, "source": "quotient"})
    return post(url, body=json.dumps(msg).encode("utf-8"), headers={"Content-Type": "application/json"})


SENDERS = {"telegram": send_telegram, "ntfy": send_ntfy, "webhook": send_webhook}


def send(title, body, link=None, cfg=None, raise_errors=False):
    """Sends the notice to every way that is set up. Returns {way: True/False/error text} for the ones set up."""
    phone = (cfg or q_settings.config()).get("phone") or {}
    done = {}
    for way, fn in SENDERS.items():
        conf = phone.get(way) or {}
        if not conf.get("enabled"):
            continue
        try:
            status = fn(conf, title, body, link)
            done[way] = "not set up (missing token, chat or address)" if status is None else (200 <= status < 300)
        except Exception as e:  # the secret is never in the message: urllib names the host, not the path
            if raise_errors:
                raise
            done[way] = "%s: %s" % (type(e).__name__, str(e).split("/bot")[0][:120])
    return done


def cmd_phone(args):
    """`phone test`: one notice to every way that is set up, and what happened."""
    cfg = q_settings.config()
    it = cfg.get("lang") == "it"
    res = send("Quotient", "Prova: le rate finite arriveranno qui." if it else "Test: finished installments will arrive here.", cfg=cfg)
    if not res:
        q_settings.out("No phone notice is set up. README, \"Notices on your phone\", says how (Telegram, ntfy, webhook).")
        return
    for way, ok in res.items():
        q_settings.out("%s: %s" % (way, "sent" if ok is True else "FAILED" if ok is False else ok))
