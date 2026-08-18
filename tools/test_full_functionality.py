"""
Full functional / load / persistence / isolation tests.
Uses a temp MediaStore + aiohttp test server (no Telegram polling).
Does not mutate bot/data/media.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "bot"
sys.path.insert(0, str(BOT_DIR))
sys.path.insert(0, str(ROOT))

os.chdir(ROOT)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from config import Settings  # noqa: E402
from services.media_store import MediaStore  # noqa: E402
import main as app_main  # noqa: E402


ADMIN_A = 8647494349
ADMIN_B = 8513574223
STRANGER = 111111111
TEST_TOKEN = "123456:TESTTOKEN"


def make_init_data(user_id: int, token: str = TEST_TOKEN) -> str:
    user = json.dumps({"id": user_id}, separators=(",", ":"))
    pairs = {
        "auth_date": "1700000000",
        "query_id": "AAEtest",
        "user": user,
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    digest = hmac.new(secret, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode({**pairs, "hash": digest})


def tiny_jpeg_data_url(marker: bytes = b"TEST") -> str:
    # Minimal valid-enough JPEG SOI/EOI with payload; MediaStore only stores bytes.
    blob = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + marker + b"\xff\xd9"
    return "data:image/jpeg;base64," + base64.b64encode(blob).decode("ascii")


def large_jpeg_data_url(size_kb: int = 400) -> str:
    blob = b"\xff\xd8" + (b"\x00" * (size_kb * 1024)) + b"\xff\xd9"
    return "data:image/jpeg;base64," + base64.b64encode(blob).decode("ascii")


def make_item(item_id: str, **kwargs) -> dict:
    photos = kwargs.pop("photos", None)
    if photos is None:
        photos = [{"id": "p1", "final": tiny_jpeg_data_url(item_id.encode()), "raw": "", "noStamp": False}]
    return {
        "id": item_id,
        "location": kwargs.get("location", "warehouse_1"),
        "weight": kwargs.get("weight", 0.5),
        "tapeColor": kwargs.get("tapeColor", "yellow"),
        "note": kwargs.get("note", "test"),
        "geo": kwargs.get("geo", {"latitude": 57.0, "longitude": 41.0, "accuracy": 8}),
        "createdAt": kwargs.get("createdAt", "2026-08-13T00:00:00.000Z"),
        "updatedAt": kwargs.get("updatedAt", "2026-08-13T00:00:00.000Z"),
        "photos": photos,
    }


@dataclass
class Result:
    name: str
    ok: bool
    detail: str
    ms: float = 0.0
    severity: str = "info"  # info | warn | crit


class Suite:
    def __init__(self) -> None:
        self.results: list[Result] = []

    def add(self, r: Result) -> None:
        self.results.append(r)
        mark = "PASS" if r.ok else ("FAIL" if r.severity == "crit" else "WARN")
        print(f"  [{mark}] {r.name} ({r.ms:.0f}ms) - {r.detail}")

    def check(self, name: str, ok: bool, detail: str, ms: float = 0, severity: str = "crit") -> bool:
        self.add(Result(name, ok, detail, ms, severity if not ok else "info"))
        return ok


def fake_settings(local_dev: bool = True) -> Settings:
    return Settings(
        bot_token=TEST_TOKEN,
        webapp_url="http://127.0.0.1:3000",
        admin_ids=frozenset({ADMIN_A, ADMIN_B}),
        database_path=str(BOT_DIR / "data" / "logistics.db"),
        host="127.0.0.1",
        port=3000,
        local_dev=local_dev,
        local_dev_user=ADMIN_A,
    )


def build_test_app(store: MediaStore, local_dev: bool = True) -> web.Application:
    app = web.Application(client_max_size=64 * 1024 * 1024)
    app["media_store"] = store
    app["settings"] = fake_settings(local_dev=local_dev)
    app.router.add_get("/health", app_main.handle_health)
    app.router.add_post("/api/auth", app_main.handle_auth)
    app.router.add_post("/api/sync-items", app_main.handle_sync_items)
    app.router.add_post("/api/sync-item", app_main.handle_sync_item)
    app.router.add_post("/api/delete-item", app_main.handle_delete_item)
    app.router.add_post("/api/inventory", app_main.handle_inventory)
    app.router.add_get("/api/photo/{item_id}/{photo_id}", app_main.handle_photo)
    return app


def test_media_store(suite: Suite, tmp: Path) -> None:
    print("\n== MediaStore persistence / isolation ==")
    store = MediaStore(tmp / "media")

    t0 = time.perf_counter()
    n = store.merge_items(ADMIN_A, [make_item("a1"), make_item("a2")])
    suite.check("merge two items", n == 2 and len(store.list_items(ADMIN_A)) == 2,
                f"saved={n} total={len(store.list_items(ADMIN_A))}",
                (time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    store.merge_items(ADMIN_B, [make_item("b1")])
    a_ids = {i["id"] for i in store.list_items(ADMIN_A)}
    b_ids = {i["id"] for i in store.list_items(ADMIN_B)}
    suite.check("admin isolation", a_ids == {"a1", "a2"} and b_ids == {"b1"},
                f"A={sorted(a_ids)} B={sorted(b_ids)}",
                (time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    orphan_id = f"stash_{ADMIN_A}_01"
    raw = store._load_items()
    raw.append({
        "id": orphan_id,
        "location": "pickup",
        "weight": 0.5,
        "tape_color": "yellow",
        "note": "orphan stamp",
        "photos": [],
        "geo": {},
    })
    store._save_items(raw)
    a_ids = {i["id"] for i in store.list_items(ADMIN_A)}
    b_ids = {i["id"] for i in store.list_items(ADMIN_B)}
    suite.check("stash id without user_id still listed for owner",
                orphan_id in a_ids and orphan_id not in b_ids,
                f"A={sorted(a_ids)} B={sorted(b_ids)}",
                (time.perf_counter() - t0) * 1000)
    store.delete_item_ids(ADMIN_A, [orphan_id])

    t0 = time.perf_counter()
    store.merge_items(ADMIN_A, [make_item("a3", note="third")])
    a_ids = {i["id"] for i in store.list_items(ADMIN_A)}
    suite.check("merge does not wipe siblings", a_ids == {"a1", "a2", "a3"},
                f"A={sorted(a_ids)}",
                (time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    before_photos = store.get_item("a1", ADMIN_A)["photos"]
    store.merge_items(ADMIN_A, [{
        "id": "a1",
        "location": "pickup",
        "weight": 1,
        "tapeColor": "black",
        "note": "meta only",
        "geo": {"latitude": 57.1, "longitude": 41.1},
        "updatedAt": "2026-08-13T01:00:00.000Z",
        "photos": [{"id": "p1", "final": "", "raw": ""}],
    }])
    after = store.get_item("a1", ADMIN_A)
    kept = bool(after and after.get("photos") and Path(after["photos"][0]["path"]).is_file())
    note_ok = after.get("note") == "meta only"
    suite.check("meta-only sync keeps photo files", kept and note_ok,
                f"kept={kept} note={after.get('note')!r} photos={len(after.get('photos') or [])}",
                (time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    removed = store.delete_item_ids(ADMIN_A, ["a2"])
    a_ids = {i["id"] for i in store.list_items(ADMIN_A)}
    b_ok = store.get_item("b1", ADMIN_B) is not None
    folder_gone = not (store.photos_dir / str(ADMIN_A) / "a2").exists()
    suite.check("point delete removes item+photos, not others",
                removed == 1 and a_ids == {"a1", "a3"} and b_ok and folder_gone,
                f"removed={removed} A={sorted(a_ids)} B_ok={b_ok} folder_gone={folder_gone}",
                (time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    store.upsert_items(ADMIN_A, [make_item("only")])
    a_ids = {i["id"] for i in store.list_items(ADMIN_A)}
    b_ok = store.get_item("b1", ADMIN_B) is not None
    suite.check("upsert replace wipes only that admin",
                a_ids == {"only"} and b_ok,
                f"A={sorted(a_ids)} B_ok={b_ok}",
                (time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    store.merge_items(ADMIN_A, [make_item("a1")])
    incoming_new_id = {
        "id": "a1",
        "location": "warehouse_1",
        "weight": 0.5,
        "tapeColor": "yellow",
        "note": "rebake ids",
        "photos": [{"id": "p_new", "final": "", "raw": ""}],
    }
    store.merge_items(ADMIN_A, [incoming_new_id])
    after = store.get_item("a1", ADMIN_A)
    photo_ids = [p.get("id") for p in (after or {}).get("photos") or []]
    # If client sends a different empty photo id, previous files may be dropped
    # unless photos_meta is empty (fallback). Here photos_meta is empty → fallback keeps old.
    suite.check("empty photos with new id: keep-or-lose",
                True,
                f"photo_ids={photo_ids} (empty incoming with unknown id, fallback={photo_ids==['p1']})",
                (time.perf_counter() - t0) * 1000,
                severity="warn")

    # Partial incoming with one matching empty id + extra prev photo
    store.merge_items(ADMIN_A, [make_item("multi", photos=[
        {"id": "p1", "final": tiny_jpeg_data_url(b"p1")},
        {"id": "p2", "final": tiny_jpeg_data_url(b"p2")},
    ])])
    store.merge_items(ADMIN_A, [{
        "id": "multi",
        "location": "warehouse_1",
        "weight": 0.5,
        "tapeColor": "yellow",
        "note": "one photo listed",
        "photos": [{"id": "p1", "final": "", "raw": ""}],
    }])
    after = store.get_item("multi", ADMIN_A)
    pids = [p.get("id") for p in (after or {}).get("photos") or []]
    suite.check("partial photo list keeps previous extras",
                set(pids) >= {"p1", "p2"},
                f"after photo ids={pids} - extra p2 dropped if client omits it",
                0, severity="warn")

    t0 = time.perf_counter()
    items = [make_item(f"load_{i}", note=f"n{i}") for i in range(80)]
    store.merge_items(ADMIN_A, items)
    total = len(store.list_items(ADMIN_A))
    catalog_size = store.items_path.stat().st_size
    suite.check("bulk merge 80 items",
                total >= 80,
                f"total={total} catalog_json={catalog_size} bytes",
                (time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    big = make_item("bigphoto", photos=[
        {"id": f"p{i}", "final": large_jpeg_data_url(250)} for i in range(5)
    ])
    store.merge_items(ADMIN_A, [big])
    rec = store.get_item("bigphoto", ADMIN_A)
    files = [Path(p["path"]) for p in rec["photos"]]
    ok_files = all(p.is_file() and p.stat().st_size > 200_000 for p in files)
    suite.check("5×250KB photos persist to disk",
                ok_files and len(files) == 5,
                f"files={len(files)} sizes={[p.stat().st_size for p in files]}",
                (time.perf_counter() - t0) * 1000)

    # Concurrent two-admin race on the same JSON file
    print("\n== Concurrent write race (two admins) ==")
    race_store = MediaStore(tmp / "race")
    race_store.merge_items(ADMIN_A, [make_item("seed_a")])
    race_store.merge_items(ADMIN_B, [make_item("seed_b")])
    errors: list[str] = []

    def writer(uid: int, prefix: str) -> None:
        try:
            for i in range(25):
                race_store.merge_items(uid, [make_item(f"{prefix}_{i}", note=str(i))])
        except Exception as exc:
            errors.append(f"{prefix}: {exc}")

    t0 = time.perf_counter()
    ta = threading.Thread(target=writer, args=(ADMIN_A, "ra"))
    tb = threading.Thread(target=writer, args=(ADMIN_B, "rb"))
    ta.start()
    tb.start()
    ta.join()
    tb.join()
    ms = (time.perf_counter() - t0) * 1000
    a_count = len(race_store.list_items(ADMIN_A))
    b_count = len(race_store.list_items(ADMIN_B))
    lost = a_count < 26 or b_count < 26  # seed + 25
    try:
        json.loads(race_store.items_path.read_text(encoding="utf-8"))
        json_ok = True
    except Exception as exc:
        json_ok = False
        errors.append(str(exc))
    suite.check("concurrent two-admin JSON writes",
                not lost and json_ok and not errors,
                f"A={a_count} (expect≥26) B={b_count} (expect≥26) json_ok={json_ok} errors={errors[:2]}",
                ms, severity="crit")


async def test_http(suite: Suite, tmp: Path) -> None:
    print("\n== HTTP API (local_dev) ==")
    store = MediaStore(tmp / "http_media")
    app = build_test_app(store, local_dev=True)

    async with TestClient(TestServer(app)) as client:
        t0 = time.perf_counter()
        res = await client.get("/health")
        body = await res.json()
        suite.check("GET /health", res.status == 200 and body.get("ok") is True,
                    f"status={res.status} body={body}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        res = await client.post("/api/auth", json={})
        body = await res.json()
        suite.check("POST /api/auth empty → local_dev user",
                    res.status == 200 and body.get("userId") == ADMIN_A,
                    f"status={res.status} body={body}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        res = await client.post("/api/auth", json={"userId": ADMIN_B})
        body = await res.json()
        suite.check("POST /api/auth second admin by userId",
                    res.status == 200 and body.get("userId") == ADMIN_B,
                    f"status={res.status} body={body}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        res = await client.post("/api/auth", json={"userId": STRANGER})
        suite.check("POST /api/auth stranger forbidden",
                    res.status == 403,
                    f"status={res.status} body={await res.json()}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        item = make_item("http_a1", note="from http")
        res = await client.post("/api/sync-item", json={"userId": ADMIN_A, "item": item})
        body = await res.json()
        suite.check("POST /api/sync-item",
                    res.status == 200 and body.get("ok") and body.get("saved") == 1,
                    f"status={res.status} body={body}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        res = await client.post("/api/inventory", json={"userId": ADMIN_A})
        body = await res.json()
        items = body.get("items") or []
        has = any(i.get("id") == "http_a1" for i in items)
        photo_url = ((items[0].get("photos") or [{}])[0].get("url") if items else None)
        no_blob = not any(
            str((p.get("final") or p.get("raw") or "")).startswith("data:")
            for i in items for p in (i.get("photos") or [])
        )
        suite.check("POST /api/inventory returns meta without blobs",
                    has and no_blob and photo_url,
                    f"count={body.get('count')} has={has} photo_url={photo_url} no_blob={no_blob}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        res = await client.get(f"/api/photo/http_a1/p1?userId={ADMIN_A}")
        raw = await res.read()
        suite.check("GET /api/photo with userId",
                    res.status == 200 and raw[:2] == b"\xff\xd8",
                    f"status={res.status} bytes={len(raw)} ctype={res.headers.get('Content-Type')}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        res = await client.get("/api/photo/http_a1/p1")
        # local_dev without userId falls back to LOCAL_DEV_USER = ADMIN_A, so this succeeds
        suite.check("GET /api/photo without userId (local_dev fallback)",
                    res.status == 200,
                    f"status={res.status} - local_dev maps to ADMIN_A",
                    (time.perf_counter() - t0) * 1000, severity="warn")

        t0 = time.perf_counter()
        res = await client.get(f"/api/photo/http_a1/p1?userId={ADMIN_B}")
        suite.check("GET /api/photo other admin cannot read",
                    res.status in {403, 404},
                    f"status={res.status} body={(await res.text())[:120]}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        res = await client.post("/api/sync-item", json={"userId": ADMIN_B, "item": make_item("http_b1")})
        inv_a = await (await client.post("/api/inventory", json={"userId": ADMIN_A})).json()
        inv_b = await (await client.post("/api/inventory", json={"userId": ADMIN_B})).json()
        a_ids = {i["id"] for i in inv_a.get("items") or []}
        b_ids = {i["id"] for i in inv_b.get("items") or []}
        suite.check("HTTP isolation between admins",
                    "http_a1" in a_ids and "http_b1" not in a_ids and "http_b1" in b_ids and "http_a1" not in b_ids,
                    f"A={sorted(a_ids)} B={sorted(b_ids)}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        # merge extra item for A, ensure a1 still there
        await client.post("/api/sync-item", json={"userId": ADMIN_A, "item": make_item("http_a2")})
        inv_a = await (await client.post("/api/inventory", json={"userId": ADMIN_A})).json()
        a_ids = {i["id"] for i in inv_a.get("items") or []}
        suite.check("second sync-item does not wipe first",
                    {"http_a1", "http_a2"} <= a_ids,
                    f"A={sorted(a_ids)}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        res = await client.post("/api/delete-item", json={"userId": ADMIN_A, "itemId": "http_a2"})
        body = await res.json()
        inv_a = await (await client.post("/api/inventory", json={"userId": ADMIN_A})).json()
        a_ids = {i["id"] for i in inv_a.get("items") or []}
        suite.check("POST /api/delete-item",
                    body.get("removed") == 1 and "http_a2" not in a_ids and "http_a1" in a_ids,
                    f"body={body} A={sorted(a_ids)}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        res = await client.post("/api/sync-items", json={
            "userId": ADMIN_A,
            "replace": True,
            "items": [make_item("replaced_only")],
        })
        inv_a = await (await client.post("/api/inventory", json={"userId": ADMIN_A})).json()
        a_ids = {i["id"] for i in inv_a.get("items") or []}
        inv_b = await (await client.post("/api/inventory", json={"userId": ADMIN_B})).json()
        b_ids = {i["id"] for i in inv_b.get("items") or []}
        suite.check("replace:true is ignored (merge only)",
                    "replaced_only" in a_ids and "http_a1" in a_ids and "http_b1" in b_ids,
                    f"A={sorted(a_ids)} B={sorted(b_ids)}",
                    (time.perf_counter() - t0) * 1000)

        # Resurrection: local pull-merge model (server-side we can only show delete is point-delete)
        t0 = time.perf_counter()
        await client.post("/api/sync-item", json={"userId": ADMIN_A, "item": make_item("ghost")})
        await client.post("/api/delete-item", json={"userId": ADMIN_A, "itemId": "ghost"})
        # Client still holding ghost locally would re-merge it:
        await client.post("/api/sync-items", json={"userId": ADMIN_A, "items": [make_item("ghost", photos=[])]})
        inv_a = await (await client.post("/api/inventory", json={"userId": ADMIN_A})).json()
        a_ids = {i["id"] for i in inv_a.get("items") or []}
        suite.check("deleted item stays deleted (no resurrection)",
                    "ghost" not in a_ids,
                    "no tombstones - second device / stale localStorage re-uploads deleted stash",
                    (time.perf_counter() - t0) * 1000, severity="warn")

        print("\n== HTTP load ==")
        t0 = time.perf_counter()
        batch = [make_item(f"http_load_{i}", photos=[{"id": "p1", "final": tiny_jpeg_data_url()}]) for i in range(40)]
        res = await client.post("/api/sync-items", json={"userId": ADMIN_A, "items": batch})
        body = await res.json()
        suite.check("POST /api/sync-items 40 items",
                    res.status == 200 and body.get("ok"),
                    f"status={res.status} saved={body.get('saved')} total={body.get('total')}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        tasks = [
            client.post("/api/inventory", json={"userId": ADMIN_A})
            for _ in range(30)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        ok_n = sum(1 for r in results if not isinstance(r, Exception) and r.status == 200)
        suite.check("30 concurrent /api/inventory",
                    ok_n == 30,
                    f"ok={ok_n}/30",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        huge = make_item("huge", photos=[{"id": f"p{i}", "final": large_jpeg_data_url(900)} for i in range(5)])
        payload = json.dumps({"userId": ADMIN_A, "item": huge})
        payload_mb = len(payload) / (1024 * 1024)
        res = await client.post("/api/sync-item", data=payload, headers={"Content-Type": "application/json"})
        body = await res.json() if res.status == 200 else {"status": res.status, "text": (await res.text())[:200]}
        suite.check("POST /api/sync-item ~5×900KB photos (under 64MB)",
                    res.status == 200 and (body.get("ok") is True),
                    f"payload={payload_mb:.1f}MB status={res.status} body={body}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        oversize = "A" * (65 * 1024 * 1024)
        res = await client.post("/api/sync-item", data=oversize, headers={"Content-Type": "application/json"})
        suite.check("payload >64MB rejected",
                    res.status in {413, 400},
                    f"status={res.status}",
                    (time.perf_counter() - t0) * 1000, severity="warn")


async def test_http_production_auth_hole(suite: Suite, tmp: Path) -> None:
    print("\n== Auth without Telegram initData (production-like) ==")
    store = MediaStore(tmp / "prod_auth")
    store.merge_items(ADMIN_A, [make_item("secret_stash")])
    app = build_test_app(store, local_dev=False)

    async with TestClient(TestServer(app)) as client:
        t0 = time.perf_counter()
        res = await client.post("/api/auth", json={})
        suite.check("prod: empty auth rejected",
                    res.status in {401, 403},
                    f"status={res.status} body={await res.json()}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        res = await client.post("/api/inventory", json={"userId": ADMIN_A})
        body = await res.json()
        leaked = res.status == 200 and body.get("ok") and any(i.get("id") == "secret_stash" for i in body.get("items") or [])
        suite.check("prod: inventory by known admin userId WITHOUT initData",
                    not leaked,
                    f"status={res.status} leaked={leaked} count={body.get('count')} - anyone who knows ADMIN_IDS can read/write warehouse",
                    (time.perf_counter() - t0) * 1000, severity="crit")

        t0 = time.perf_counter()
        fake_init = "user=" + json.dumps({"id": ADMIN_A}, separators=(",", ":"))
        res = await client.post("/api/inventory", json={"initData": fake_init})
        body = await res.json()
        leaked2 = res.status == 200 and body.get("ok")
        suite.check("prod: unsigned forged initData rejected",
                    not leaked2,
                    f"status={res.status} accepted={leaked2}",
                    (time.perf_counter() - t0) * 1000, severity="crit")

        t0 = time.perf_counter()
        init = make_init_data(ADMIN_A)
        res = await client.post(
            "/api/inventory",
            json={"initData": init},
            headers={"X-Telegram-Init-Data": init},
        )
        body = await res.json()
        suite.check("prod: valid initData can read inventory",
                    res.status == 200 and body.get("ok") is True and body.get("count") == 1,
                    f"status={res.status} count={body.get('count')}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        res = await client.get(f"/api/photo/secret_stash/p1?userId={ADMIN_A}")
        suite.check("prod: photo by userId without initData rejected",
                    res.status in {401, 403},
                    f"status={res.status}",
                    (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        res = await client.get(
            "/api/photo/secret_stash/p1",
            headers={"X-Telegram-Init-Data": init},
        )
        raw = await res.read()
        suite.check("prod: photo with valid initData header",
                    res.status == 200 and raw[:2] == b"\xff\xd8",
                    f"status={res.status} bytes={len(raw)}",
                    (time.perf_counter() - t0) * 1000)


def test_live_catalog(suite: Suite) -> None:
    print("\n== Live local catalog (read-only) ==")
    media = BOT_DIR / "data" / "media"
    store = MediaStore(media)
    items = store.list_items()
    by_user: dict[int, int] = {}
    missing_photos = 0
    total_photos = 0
    for it in items:
        uid = int(it.get("user_id") or 0)
        by_user[uid] = by_user.get(uid, 0) + 1
        for p in it.get("photos") or []:
            total_photos += 1
            path = Path(p.get("path") or "")
            if not path.is_file():
                missing_photos += 1
    catalog_bytes = store.items_path.stat().st_size if store.items_path.exists() else 0
    photo_bytes = 0
    if store.photos_dir.exists():
        for f in store.photos_dir.rglob("*.jpg"):
            try:
                photo_bytes += f.stat().st_size
            except OSError:
                pass
    suite.check("local catalog readable",
                True,
                f"items={len(items)} by_user={by_user} photos={total_photos} missing_files={missing_photos} "
                f"catalog_json={catalog_bytes}B photo_disk={photo_bytes/1024/1024:.1f}MB",
                0, severity="warn" if missing_photos else "info")
    loc6 = [i for i in items if i.get("id") == "stash_8647494349_06"]
    if loc6:
        n = len(loc6[0].get("photos") or [])
        suite.check("loc6 photo count",
                    n >= 2,
                    f"stash_06 photos={n} (known: one photo if blue bottle skipped)",
                    0, severity="warn")


async def probe_production(suite: Suite) -> None:
    print("\n== Production Bothost (read-only probe) ==")
    import aiohttp

    base = "https://gekgekau.bothost.tech"
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            t0 = time.perf_counter()
            async with session.get(base + "/health") as res:
                text = await res.text()
                suite.check("prod GET /health",
                            res.status == 200 and "ok" in text.lower(),
                            f"status={res.status} body={text[:180]}",
                            (time.perf_counter() - t0) * 1000)

            t0 = time.perf_counter()
            async with session.post(base + "/api/auth", json={"userId": ADMIN_A}) as res:
                body = await res.json(content_type=None)
                suite.check("prod POST /api/auth with only userId",
                            res.status in {401, 403},
                            f"status={res.status} body={body} (401 after redeploy)",
                            (time.perf_counter() - t0) * 1000, severity="warn")

            t0 = time.perf_counter()
            async with session.post(base + "/api/inventory", json={"userId": ADMIN_A}) as res:
                body = await res.json(content_type=None)
                suite.check("prod inventory without initData",
                            res.status in {401, 403},
                            f"status={res.status} (401 after redeploy)",
                            (time.perf_counter() - t0) * 1000, severity="warn")
    except Exception as exc:
        suite.check("prod reachable", False, f"{type(exc).__name__}: {exc}", 0, severity="warn")


def test_client_static(suite: Suite) -> None:
    print("\n== Client static checks ==")
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    public = (BOT_DIR / "public" / "index.html").read_text(encoding="utf-8")
    suite.check("root index.html == bot/public/index.html",
                html == public,
                f"root={len(html)} public={len(public)} chars",
                0, severity="warn")
    suite.check("client has /api/sync-item",
                "/api/sync-item" in html, "syncItemToServer present")
    suite.check("client has /api/delete-item",
                "/api/delete-item" in html, "deleteItemOnServer present")
    suite.check("client does not send replace:true",
                "replace: true" not in html and '"replace": true' not in html,
                "no full-replace flag in client")
    suite.check("GPS required before save",
                "нет GPS — фото нельзя" in html, "save blocked without geo")
    suite.check("shutter snapshots geo",
                "snapshotGeoForCapture" in html and "addQuickPhoto(dataUrl, snap)" in html,
                "capture stamps geo on photo")
    suite.check("toSync copy before quota strip",
                "const toSync" in html and "syncItemToServer(toSync" in html,
                "baked photos copied before persist/strip")


async def amain() -> int:
    suite = Suite()
    print("Logistics bot - functional / load / persistence audit")
    test_client_static(suite)
    test_live_catalog(suite)

    with tempfile.TemporaryDirectory(prefix="logistics_test_") as raw:
        tmp = Path(raw)
        test_media_store(suite, tmp)
        await test_http(suite, tmp)
        await test_http_production_auth_hole(suite, tmp)

    await probe_production(suite)

    passed = sum(1 for r in suite.results if r.ok)
    failed = [r for r in suite.results if not r.ok]
    crit = [r for r in failed if r.severity == "crit"]
    warn = [r for r in failed if r.severity != "crit"]
    print("\n== SUMMARY ==")
    print(f"  total={len(suite.results)} passed={passed} failed={len(failed)} (crit={len(crit)} warn={len(warn)})")
    if crit:
        print("  CRITICAL:")
        for r in crit:
            print(f"    - {r.name}: {r.detail}")
    if warn:
        print("  WEAK / WARN:")
        for r in warn:
            print(f"    - {r.name}: {r.detail}")
    return 1 if crit else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
