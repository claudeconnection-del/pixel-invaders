"""Offline score outbox: submissions that couldn't reach the arcade server
are queued in the profile and retried on the next successful contact —
so away-from-home runs still land on the global boards eventually.

Items: {"id", "type": "score"|"session", "game", "mode", "code",
        "name", "score", "wave", "date"}
Kept on network failure, dropped on success or definitive 4xx rejection
(e.g. an expired session).
"""
import uuid
from datetime import datetime, timezone

MAX_ITEMS = 50


class Outbox:
    def __init__(self, profile, net, on_rank=None, save_cb=None):
        self.profile = profile
        self.net = net
        self.on_rank = on_rank or (lambda rank: None)
        self.save_cb = save_cb or (lambda: None)
        self.inflight = set()

    @property
    def items(self):
        return self.profile.setdefault("outbox", [])

    def queue_score(self, game, mode, name, score, wave=None):
        self._enqueue({"type": "score", "game": game, "mode": mode,
                       "name": name, "score": int(score), "wave": wave})

    def queue_session_score(self, code, name, score, wave=None):
        self._enqueue({"type": "session", "code": code, "name": name,
                       "score": int(score), "wave": wave})

    def _enqueue(self, item):
        item["id"] = uuid.uuid4().hex[:12]
        item["date"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.items.append(item)
        del self.items[:-MAX_ITEMS]  # cap oldest-first
        self.save_cb()
        self.drain()

    def drain(self):
        """Fire pending submissions (skipping ones already in flight)."""
        if not self.net.available:
            return
        for item in list(self.items):
            if item["id"] in self.inflight:
                continue
            self.inflight.add(item["id"])
            tag = ("outbox", item["id"])
            if item["type"] == "score":
                self.net.submit_score(item["game"], item["mode"], item["name"],
                                      item["score"], item.get("wave"), tag=tag)
            else:
                self.net.submit_session_score(item["code"], item["name"],
                                              item["score"], item.get("wave"),
                                              tag=tag)

    def handle_result(self, tag, payload):
        """Feed ("outbox", id) results from ArcadeClient.poll() here."""
        item_id = tag[1]
        self.inflight.discard(item_id)
        item = next((i for i in self.items if i["id"] == item_id), None)
        if item is None:
            return
        if payload is None:
            return  # offline / transient: stays queued
        status = payload.get("__status__") if isinstance(payload, dict) else None
        if status is not None and not (400 <= status < 500):
            return  # 5xx: server hiccup, retry later
        # success or definitive 4xx rejection: either way it leaves the queue
        self.items.remove(item)
        self.save_cb()
        if status is None and item["type"] == "score" and "rank" in payload:
            self.on_rank(payload["rank"])
