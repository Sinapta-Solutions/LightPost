import asyncio
import base64
import tempfile
import unittest
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from lightpost.app import KEYS, create_app, iso_time
from lightpost.config import Config
from lightpost.jobs import Scheduler, delivery_status
from lightpost.providers import (
    ProviderError,
    Providers,
    bluesky_record_key,
    instance_url,
    now,
    oauth_header,
    public_ip,
    text_length,
)
from lightpost.security import Vault
from lightpost.store import Store

warnings.filterwarnings("ignore", category=web.NotAppKeyWarning)
KEY = "a1" * 32  # Test-only key, not a real credential.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jM1sAAAAASUVORK5CYII="
)


def future(seconds=3600):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def post(id="p1", **changes):
    return {
        "id": id,
        "text": "A real idea.",
        "accountIds": ["a", "b"],
        "mediaIds": [],
        "status": "queued",
        "scheduledAt": None,
        "createdAt": now(),
        "results": [],
        **changes,
    }


class ConfigTests(unittest.TestCase):
    def test_password_length_and_loopback_requirements(self):
        for host, password, valid in [
            ("0.0.0.0", "", False),
            ("0.0.0.0", "a", True),
            ("0.0.0.0", "a" * 8, True),
            ("0.0.0.0", "a" * 9, False),
            ("0.0.0.0", "a" * 16, False),
            ("127.0.0.1", "", True),
            ("localhost", "", True),
            ("::1", "", True),
            ("127.0.0.1", "a" * 8, True),
            ("127.0.0.1", "a" * 9, False),
        ]:
            with (
                self.subTest(host=host, length=len(password)),
                patch.dict("os.environ", {"HOST": host, "ADMIN_PASSWORD": password}, clear=True),
                patch("lightpost.config.load_env"),
            ):
                if valid:
                    self.assertEqual(Config.from_env().password, password)
                else:
                    with self.assertRaisesRegex(ValueError, "ADMIN_PASSWORD"):
                        Config.from_env()


class CoreTests(unittest.TestCase):
    def test_delivery_status_prioritizes_unresolved_destinations(self):
        for statuses, expected in [
            (["published", "published"], "published"),
            (["simulated", "simulated"], "simulated"),
            (["published", "simulated"], "published"),
            (["failed", "failed"], "failed"),
            (["published", "failed"], "partial"),
            (["simulated", "failed"], "partial"),
            (["published", "processing", "failed"], "processing"),
            (["uncertain", "processing", "failed", "published"], "needs_review"),
        ]:
            with self.subTest(statuses=statuses):
                self.assertEqual(delivery_status(statuses), expected)
                self.assertEqual(delivery_status(list(reversed(statuses))), expected)

    def test_bluesky_record_keys_are_valid_stable_and_distinct(self):
        value = post(createdAt="2026-10-27T04:40:31.483Z")
        key = bluesky_record_key(value)
        self.assertRegex(key, r"^[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}$")
        self.assertEqual(key, bluesky_record_key({**value, "deliveryAt": now()}))
        keys = {bluesky_record_key({**value, "id": f"post-{i}"}) for i in range(100)}
        self.assertEqual(len(keys), 100)
        alphabet = "234567abcdefghijklmnopqrstuvwxyz"
        decoded = 0
        for char in key:
            decoded = decoded * 32 + alphabet.index(char)
        self.assertEqual((decoded >> 10) // 1000, 1793076031483)

    def test_vault_random_nonces_and_tamper_rejection(self):
        vault = Vault(KEY)
        first = vault.encrypt({"token": "TEST_ONLY"})
        second = vault.encrypt({"token": "TEST_ONLY"})
        self.assertNotEqual(first, second)
        self.assertNotIn("TEST_ONLY", first)
        self.assertEqual(vault.decrypt(first), {"token": "TEST_ONLY"})
        with self.assertRaisesRegex(ValueError, "Cannot unlock"):
            Vault("b2" * 32).decrypt(first)
        with self.assertRaises(ValueError):
            vault.decrypt(first[:-2] + "ff")

    def test_generated_key_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            encrypted = Vault(directory=directory).encrypt({"token": "test"})
            self.assertEqual(Vault(directory=directory).decrypt(encrypted)["token"], "test")
            self.assertEqual((Path(directory) / "credentials.key").stat().st_mode & 0o777, 0o600)

    def test_instance_address_restrictions(self):
        for value in [
            "http://mastodon.social",
            "https://127.0.0.1",
            "https://10.2.3.4",
            "https://169.254.169.254",
            "https://user:password@example.com",
            "https://example.com:443",
            "https://example.com/path",
            "https://server.local",
            "https://example.com#fragment",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                instance_url(value)
        self.assertEqual(instance_url("https://mastodon.social/"), "https://mastodon.social")
        for value in ["127.0.0.1", "::1", "::ffff:127.0.0.1", "100.64.0.1", "224.0.0.1"]:
            self.assertFalse(public_ip(value))
        self.assertTrue(public_ip("8.8.8.8"))

    def test_unicode_limits(self):
        self.assertEqual(text_length("bluesky", "👨‍👩‍👧‍👦"), 1)
        self.assertEqual(text_length("x", "👨‍👩‍👧‍👦"), 2)
        self.assertEqual(text_length("x", "你好"), 4)
        self.assertEqual(text_length("x", "cafe\u0301"), 4)
        self.assertEqual(text_length("x", "https://example.org/long/path"), 23)

    def test_dates_require_timezone_and_normalize_to_utc(self):
        self.assertEqual(iso_time("2027-02-01T10:00:00-05:00"), "2027-02-01T15:00:00.000Z")
        with self.assertRaises(ValueError):
            iso_time("2027-02-01T10:00:00")

    def test_oauth_rfc5849_signature(self):
        header = oauth_header(
            "GET",
            "http://photos.example.net/photos?file=vacation.jpg&size=original",
            {
                "apiKey": "dpf43f3p2l4k3l03",
                "apiSecret": "kd94hf93k423kf44",
                "token": "nnch734d00sl2jdk",
                "tokenSecret": "pfkkdhi9sl3r4s00",
            },
            nonce="kllo9940pd9333jh",
            timestamp=1191242096,
        )
        self.assertIn('oauth_signature="tR3%2BTy81lMeYAr%2FFid0kMTYa%2FWM%3D"', header)


class StoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_persistence_private_database_and_single_process_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "lightpost.sqlite")
            store = await Store(path).open()
            await store.put("posts", post())
            other = Store(path)
            with self.assertRaisesRegex(ValueError, "Another LightPost"):
                await other.open()
            await store.close()
            self.assertFalse(Path(path + ".before-python.bak").exists())
            self.assertEqual(Path(path).stat().st_mode & 0o777, 0o600)
            store = await Store(path).open()
            self.assertEqual((await store.get("posts", "p1"))["text"], "A real idea.")
            await store.close()

    async def test_due_query_and_attention_pagination(self):
        store = await Store(":memory:").open()
        try:
            await store.put(
                "posts", post("past", status="scheduled", scheduledAt="2020-01-01T00:00:00.000Z")
            )
            await store.put(
                "posts", post("future", status="scheduled", scheduledAt="2099-01-01T00:00:00.000Z")
            )
            await store.put("posts", post("failed", status="failed"))
            self.assertEqual([p["id"] for p in await store.due(now())], ["past"])
            rows, total = await store.posts("attention")
            self.assertEqual(total, 1)
            self.assertEqual(rows[0]["id"], "failed")
        finally:
            await store.close()


class JobTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = await Store(":memory:").open()
        self.providers = Providers(Vault(KEY), AsyncMock())
        self.jobs = Scheduler(self.store, self.providers, self.directory.name, interval=0.01)
        for id in ("a", "b", "c", "d"):
            await self.store.put(
                "accounts",
                {"id": id, "platform": "bluesky", "name": "Test", "handle": "@demo", "demo": True},
            )

    async def asyncTearDown(self):
        await self.jobs.close()
        await self.store.close()
        self.directory.cleanup()

    async def test_content_toggles_filter_each_destination_independently(self):
        value = post(
            mediaIds=["image"], contentOptions={"a": {"text": False}, "b": {"image": False}}
        )
        await self.store.put("posts", value)
        self.providers.publish = AsyncMock(return_value={"status": "simulated"})
        images = [{"id": "image", "bytes": PNG}]
        await self.jobs.destination(value, "a", images)
        await self.jobs.destination(value, "b", images)
        first, second = self.providers.publish.call_args_list
        self.assertEqual(first.args[1]["text"], "")
        self.assertEqual(first.args[2], images)
        self.assertEqual(second.args[1]["text"], value["text"])
        self.assertEqual(second.args[1]["mediaIds"], [])
        self.assertEqual(second.args[2], [])
        self.assertEqual(value["mediaIds"], ["image"])
        self.assertNotEqual(value["text"], "")

    async def test_demo_delivery_never_requests_network(self):
        await self.store.put("posts", post())
        await self.jobs.tick()
        result = await self.store.get("posts", "p1")
        self.assertEqual(result["status"], "simulated")
        self.assertEqual(len([r for r in result["results"] if r["status"] == "simulated"]), 2)
        self.providers.send.assert_not_called()

    async def test_destinations_run_concurrently(self):
        started = set()
        both_started = asyncio.Event()

        async def publish(account, *_):
            started.add(account["id"])
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=1)
            return {"status": "published"}

        self.providers.publish = publish
        await self.store.put("posts", post())
        await self.jobs.tick()
        self.assertEqual((await self.store.get("posts", "p1"))["status"], "published")

    async def test_retry_skips_successes_and_keeps_failure_receipts(self):
        attempts = []

        async def publish(account, *_):
            attempts.append(account["id"])
            if account["id"] == "b" and len(attempts) == 2:
                raise ProviderError("Permission denied.", status=403)
            return {"status": "published"}

        self.providers.publish = publish
        await self.store.put("posts", post())
        await self.jobs.tick()
        saved = await self.store.get("posts", "p1")
        self.assertEqual(saved["status"], "partial")
        await self.store.put("posts", {**saved, "status": "queued"})
        await self.jobs.tick()
        self.assertEqual(attempts.count("a"), 1)
        self.assertEqual(attempts.count("b"), 2)
        self.assertEqual((await self.store.get("posts", "p1"))["status"], "published")

    async def test_restart_requires_review_without_reposting_success(self):
        await self.store.put(
            "posts",
            post(
                status="publishing",
                results=[
                    {"accountId": "a", "status": "published"},
                    {"accountId": "b", "status": "sending"},
                ],
            ),
        )
        await self.jobs.recover()
        saved = await self.store.get("posts", "p1")
        self.assertEqual(saved["status"], "needs_review")
        self.assertEqual(saved["results"][-1]["status"], "uncertain")
        await self.jobs.tick()
        self.providers.send.assert_not_called()

    async def test_unknown_network_outcome_is_not_automatically_retried(self):
        self.providers.publish = AsyncMock(side_effect=ProviderError("Interrupted", uncertain=True))
        await self.store.put("posts", post(accountIds=["a"]))
        await self.jobs.tick()
        self.assertEqual((await self.store.get("posts", "p1"))["status"], "needs_review")
        await self.jobs.tick()
        self.assertEqual(self.providers.publish.await_count, 1)

    async def test_duplicate_claim_and_same_account_serialization(self):
        active, maximum = 0, 0

        async def publish(*_):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {"status": "published"}

        self.providers.publish = AsyncMock(side_effect=publish)
        await self.store.put("posts", post("p1", accountIds=["a"]))
        await self.store.put("posts", post("p2", accountIds=["a"]))
        await asyncio.gather(
            self.jobs.deliver("p1"), self.jobs.deliver("p1"), self.jobs.deliver("p2")
        )
        self.assertEqual(maximum, 1)
        self.assertEqual(self.providers.publish.await_count, 2)

    async def test_global_delivery_limit(self):
        active, maximum = 0, 0

        async def publish(*_):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.02)
            active -= 1
            return {"status": "published"}

        self.providers.publish = publish
        await self.store.put("posts", post(accountIds=["a", "b", "c", "d"]))
        await self.jobs.tick()
        self.assertEqual(maximum, 3)

    async def test_unsupported_platform_schedule_is_blocked(self):
        account = {
            "id": "old",
            "name": "TikTok",
            "platform": "tiktok",
            "credentials": "encrypted-test-value",
        }
        await self.store.put("accounts", account)
        await self.store.put(
            "posts",
            post(accountIds=["old"], status="scheduled", scheduledAt="2020-01-01T00:00:00.000Z"),
        )
        await self.jobs.recover()
        self.assertEqual((await self.store.get("posts", "p1"))["status"], "blocked")
        self.assertEqual(
            (await self.store.get("accounts", "old"))["credentials"], account["credentials"]
        )

    async def test_real_loop_delivers_missed_schedule(self):
        await self.store.put(
            "posts", post(status="scheduled", scheduledAt="2020-01-01T00:00:00.000Z")
        )
        await self.jobs.start()
        for _ in range(100):
            if (await self.store.get("posts", "p1"))["status"] == "simulated":
                break
            await asyncio.sleep(0.01)
        self.assertEqual((await self.store.get("posts", "p1"))["status"], "simulated")


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_bluesky_session_rotation_blob_and_stable_record(self):
        send = AsyncMock(
            side_effect=[
                {
                    "accessJwt": "test-access",
                    "refreshJwt": "test-refresh",
                    "did": "did:plc:test",
                    "handle": "test.bsky.social",
                },
                {"blob": {"ref": {"$link": "test-blob"}}},
                {"uri": "at://did:plc:test/app.bsky.feed.post/p1"},
            ]
        )
        vault = Vault(KEY)
        account = {
            "id": "a",
            "name": "Bluesky",
            "platform": "bluesky",
            "credentials": vault.encrypt(
                {"refreshJwt": "old-test", "identifier": "test", "password": "app-test"}
            ),
        }
        save = AsyncMock()
        result = await Providers(vault, send).publish(
            account,
            post(text="hi https://example.org", deliveryAt=now(), mediaIds=["image"]),
            [{"bytes": PNG, "mime": "image/png", "name": "test.png", "alt": "A dot"}],
            save,
        )
        self.assertEqual(result["status"], "published")
        save.assert_awaited_once()
        record = send.call_args_list[-1].kwargs["json"]
        self.assertRegex(
            record["rkey"], r"^[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}$"
        )
        self.assertTrue(result["url"].endswith("/" + record["rkey"]))
        self.assertEqual(record["record"]["embed"]["images"][0]["alt"], "A dot")
        self.assertEqual(record["record"]["facets"][0]["index"]["byteStart"], 3)

    async def test_mastodon_images_and_idempotency(self):
        send = AsyncMock(side_effect=[{"id": "image-1"}, {"url": "https://example.org/@test/1"}])
        vault = Vault(KEY)
        account = {
            "id": "a",
            "name": "Mastodon",
            "platform": "mastodon",
            "credentials": vault.encrypt({"instance": "https://example.org", "token": "test"}),
        }
        result = await Providers(vault, send).publish(
            account,
            post(deliveryAt=now()),
            [{"bytes": PNG, "mime": "image/png", "name": "dot.png"}],
            AsyncMock(),
        )
        self.assertEqual(result["status"], "published")
        request = send.call_args_list[-1]
        self.assertEqual(request.kwargs["headers"]["Idempotency-Key"], "p1:a")
        self.assertEqual(request.kwargs["json"]["media_ids"], ["image-1"])

    async def test_x_verifies_identity_and_sends_signed_text(self):
        send = AsyncMock(
            side_effect=[{"data": {"id": "1", "username": "test"}}, {"data": {"id": "99"}}]
        )
        providers = Providers(Vault(KEY), send)
        account = await providers.connect(
            {
                "platform": "x",
                "secret": "test-token",
                "apiKey": "test-key",
                "apiSecret": "test-secret",
                "tokenSecret": "test-token-secret",
            }
        )
        self.assertEqual(account["handle"], "@test")
        result = await providers.publish(
            {**account, "id": "a"}, post(deliveryAt=now()), [], AsyncMock()
        )
        self.assertEqual(result["url"], "https://x.com/i/status/99")
        self.assertTrue(send.call_args.kwargs["headers"]["Authorization"].startswith("OAuth "))
        self.assertEqual(send.call_args.kwargs["json"], {"text": "A real idea."})


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.send = AsyncMock()
        self.config = Config(
            database=str(Path(self.directory.name) / "test.sqlite"), key=KEY, scheduler=False
        )
        self.client = TestClient(TestServer(create_app(self.config, self.send)))
        await self.client.start_server()
        self.store = self.client.server.app[KEYS["store"]]
        self.jobs = self.client.server.app[KEYS["jobs"]]
        for platform in ("bluesky", "mastodon"):
            await self.store.put(
                "accounts",
                {
                    "id": "test-" + platform,
                    "platform": platform,
                    "name": "Test account",
                    "handle": "@test",
                    "demo": False,
                },
            )
        self.client.server.app[KEYS["providers"]].publish = AsyncMock(
            return_value={"status": "published"}
        )

    async def asyncTearDown(self):
        await self.client.close()
        self.directory.cleanup()

    async def create_post(self, **changes):
        return await self.client.post(
            "/api/posts",
            json={
                "text": "Hello",
                "accountIds": ["test-bluesky", "test-mastodon"],
                "mediaIds": [],
                "status": "draft",
                **changes,
            },
        )

    async def test_content_options_persist_and_reject_empty_destinations(self):
        options = {"test-bluesky": {"image": False}}
        response = await self.create_post(contentOptions=options)
        self.assertEqual(response.status, 201)
        saved = await self.store.get("posts", (await response.json())["id"])
        self.assertEqual(saved["contentOptions"], options)
        response = await self.create_post(
            status="now", contentOptions={"test-bluesky": {"text": False, "image": False}}
        )
        self.assertEqual(response.status, 400)
        self.assertIn("no content", (await response.json())["error"])
        self.assertEqual(
            (await self.create_post(contentOptions={"test-bluesky": {"text": "false"}})).status, 400
        )

    async def test_x_requires_cost_confirmation_and_explicit_link_opt_in(self):
        await self.store.put(
            "accounts", {"id": "test-x", "platform": "x", "name": "X", "handle": "@test"}
        )
        payload = {"accountIds": ["test-x"], "status": "now"}
        self.assertEqual((await self.create_post(**payload)).status, 400)
        self.assertEqual((await self.create_post(**payload, xCostConfirmed=True)).status, 202)
        for url in ("https://example.com", "www.example.com", "example.com"):
            self.assertEqual(
                (await self.create_post(**payload, text=url, xCostConfirmed=True)).status, 400
            )
            response = await self.create_post(
                **payload, text=url, xCostConfirmed=True, xAllowLinks=True
            )
            self.assertEqual(response.status, 202)
            self.assertTrue((await response.json())["xAllowLinks"])
        self.assertEqual(
            (await self.create_post(accountIds=["test-x"], text="https://example.com")).status, 201
        )

    async def test_retry_cost_confirmation_only_for_unsuccessful_x_accounts(self):
        await self.store.put("accounts", {"id": "test-x", "platform": "x", "name": "X (Twitter)"})
        for x_status in ("published", "simulated", "failed", "uncertain", None):
            results = [{"accountId": "test-x", "status": "failed"}]
            if x_status:
                results.append({"accountId": "test-x", "status": x_status})
            await self.store.put(
                "posts",
                post(status="partial", accountIds=["test-x", "test-bluesky"], results=results),
            )
            response = await self.client.post("/api/posts/p1/retry", json={})
            if x_status in ("published", "simulated"):
                self.assertEqual(response.status, 202)
            else:
                self.assertEqual(response.status, 400)
                self.assertIn("X (Twitter) API cost", (await response.json())["error"])
                response = await self.client.post(
                    "/api/posts/p1/retry", json={"xCostConfirmed": True}
                )
                self.assertEqual(response.status, 202)

    async def test_multi_account_create_and_mock_publish(self):
        response = await self.create_post(
            status="now", accountIds=["test-bluesky", "test-mastodon", "test-bluesky"]
        )
        self.assertEqual(response.status, 202)
        saved = await response.json()
        self.assertEqual(len(saved["accountIds"]), 2)
        await self.jobs.tick()
        self.assertEqual((await self.store.get("posts", saved["id"]))["status"], "published")
        self.send.assert_not_called()

    async def test_schedule_validation_cancel_and_reschedule(self):
        self.assertEqual(
            (await self.create_post(status="scheduled", scheduledAt="2020-01-01T00:00:00Z")).status,
            400,
        )
        response = await self.create_post(status="scheduled", scheduledAt=future())
        self.assertEqual(response.status, 201)
        saved = await response.json()
        self.assertTrue(saved["scheduledAt"].endswith("Z"))
        response = await self.client.post("/api/posts/" + saved["id"] + "/cancel", json={})
        self.assertEqual((await response.json())["status"], "draft")
        self.assertEqual(
            (
                await self.create_post(id=saved["id"], status="scheduled", scheduledAt=future(7200))
            ).status,
            201,
        )

    async def test_validation_rejects_invalid_accounts_and_bodies(self):
        for changes in [
            {"accountIds": []},
            {"accountIds": ["missing"]},
            {"accountIds": [1]},
            {"text": ""},
            {"status": "published"},
        ]:
            with self.subTest(changes=changes):
                self.assertEqual((await self.create_post(**changes)).status, 400)
        self.assertEqual((await self.client.post("/api/posts", json=[])).status, 400)

    async def test_account_and_media_locks_for_scheduled_posts(self):
        response = await self.create_post(status="scheduled", scheduledAt=future())
        saved = await response.json()
        self.assertEqual((await self.client.delete("/api/accounts/test-bluesky")).status, 400)
        self.assertEqual((await self.client.delete("/api/posts/" + saved["id"])).status, 400)

    async def test_retry_needs_no_extra_confirmation_and_preserves_content(self):
        await self.store.put("posts", post(accountIds=["test-bluesky"], status="needs_review"))
        response = await self.client.post("/api/posts/p1/retry", json={})
        self.assertEqual(response.status, 202)
        self.assertEqual((await self.store.get("posts", "p1"))["text"], "A real idea.")

    async def test_cancel_processing_preserves_successes_and_stops_polling(self):
        await self.store.put(
            "posts",
            post(
                accountIds=["test-bluesky", "test-mastodon"],
                status="processing",
                results=[
                    {
                        "accountId": "test-bluesky",
                        "status": "published",
                        "url": "https://example.org/post",
                    },
                    {
                        "accountId": "test-mastodon",
                        "status": "processing",
                        "stage": "container",
                        "containerId": "12345",
                    },
                ],
            ),
        )
        response = await self.client.post("/api/posts/p1/cancel", json={})
        self.assertEqual(response.status, 200)
        saved = await response.json()
        self.assertEqual(saved["status"], "cancelled")
        latest = {r["accountId"]: r for r in saved["results"]}
        self.assertEqual(latest["test-bluesky"]["status"], "published")
        self.assertEqual(latest["test-mastodon"]["status"], "cancelled")
        self.assertIsNone(saved["nextCheckAt"])
        await self.jobs.tick()
        self.send.assert_not_awaited()
        response = await self.client.post("/api/posts/p1/retry", json={})
        self.assertEqual(response.status, 202)
        self.assertNotIn("cancelRequested", await response.json())

    async def test_cancel_in_flight_stops_before_publication_and_keeps_late_success(self):
        self.jobs.providers.publish = Providers.publish.__get__(self.jobs.providers, Providers)
        await self.store.put(
            "accounts",
            {
                "id": "threads",
                "platform": "threads",
                "name": "Threads",
                "remoteId": "12345",
                "credentials": Vault(KEY).encrypt({"token": "test-only", "userId": "12345"}),
            },
        )
        for cancel_at_publish in (False, True):
            started, resume = asyncio.Event(), asyncio.Event()

            async def send(method, url, **kwargs):
                if url.endswith("/threads"):
                    return {"id": "11111"}
                if url.endswith("/11111"):
                    if not cancel_at_publish:
                        started.set()
                        await resume.wait()
                    return {"status": "FINISHED"}
                if url.endswith("/threads_publish"):
                    started.set()
                    await resume.wait()
                    return {"id": "22222"}
                return {"permalink": "https://www.threads.net/@test/post/example"}

            self.send.side_effect = send
            self.send.reset_mock()
            await self.store.put("posts", post(accountIds=["threads"]))
            delivery = asyncio.create_task(self.jobs.deliver("p1"))
            try:
                await asyncio.wait_for(started.wait(), 2)
                response = await self.client.post("/api/posts/p1/cancel", json={})
                self.assertEqual(response.status, 200)
                self.assertEqual((await response.json())["status"], "cancelled")
                response = await self.client.post("/api/posts/p1/retry", json={})
                self.assertEqual(response.status, 400)
            finally:
                resume.set()
                await delivery
            saved = await self.store.get("posts", "p1")
            self.assertEqual(saved["status"], "cancelled")
            self.assertEqual(
                saved["results"][-1]["status"], "published" if cancel_at_publish else "cancelled"
            )
            publishes = [
                call
                for call in self.send.call_args_list
                if call.args[1].endswith("/threads_publish")
            ]
            self.assertEqual(len(publishes), int(cancel_at_publish))
            await self.jobs.tick()
            self.assertEqual(
                len(
                    [
                        call
                        for call in self.send.call_args_list
                        if call.args[1].endswith("/threads_publish")
                    ]
                ),
                int(cancel_at_publish),
            )

    async def test_published_content_cannot_be_edited(self):
        await self.store.put("posts", post(status="partial", accountIds=["test-bluesky"]))
        self.assertEqual((await self.create_post(id="p1", text="Changed")).status, 400)

    async def test_credentials_never_leave_state_or_export(self):
        await self.store.put(
            "accounts",
            {
                "id": "private",
                "name": "X",
                "platform": "x",
                "handle": "@test",
                "credentials": "ENCRYPTED_TEST_MARKER",
                "token": "PLAINTEXT_TEST_MARKER",
            },
        )
        for endpoint in ("/api/state", "/api/export"):
            body = await (await self.client.get(endpoint)).text()
            self.assertNotIn("ENCRYPTED_TEST_MARKER", body)
            self.assertNotIn("PLAINTEXT_TEST_MARKER", body)

    async def test_connect_reconnect_identity_and_duplicate_guard(self):
        self.send.return_value = {"data": {"id": "123", "username": "tester"}}
        payload = {
            "platform": "x",
            "secret": "test-token",
            "apiKey": "test-key",
            "apiSecret": "test-secret",
            "tokenSecret": "test-token-secret",
        }
        response = await self.client.post("/api/accounts", json=payload)
        self.assertEqual(response.status, 201)
        account = await response.json()
        self.assertNotIn("credentials", account)
        self.assertEqual((await self.client.post("/api/accounts", json=payload)).status, 400)
        self.assertEqual(
            (await self.client.post("/api/accounts", json={**payload, "id": account["id"]})).status,
            201,
        )
        self.send.return_value = {"data": {"id": "456", "username": "someoneelse"}}
        self.assertEqual(
            (await self.client.post("/api/accounts", json={**payload, "id": account["id"]})).status,
            400,
        )
        self.assertNotIn(
            "test-token", (await self.store.get("accounts", account["id"]))["credentials"]
        )

    async def test_reconnect_reuses_saved_secrets_and_replaces_only_changed_fields(self):
        self.send.return_value = {"data": {"id": "123", "username": "tester"}}
        payload = {
            "platform": "x",
            "secret": "saved-user-token",
            "apiKey": "saved-consumer-key",
            "apiSecret": "saved-consumer-secret",
            "tokenSecret": "saved-user-secret",
        }
        response = await self.client.post("/api/accounts", json=payload)
        account = await response.json()
        response = await self.client.get(f"/api/accounts/{account['id']}/connection")
        defaults = await response.json()
        self.assertEqual(defaults["values"], {})
        self.assertEqual(
            set(defaults["savedFields"]), {"secret", "apiKey", "apiSecret", "tokenSecret"}
        )
        self.assertNotIn("saved-", str(defaults))
        self.send.reset_mock()
        response = await self.client.post(
            "/api/accounts",
            json={
                "id": account["id"],
                "platform": "x",
                "secret": "new-user-token",
                "tokenSecret": "new-user-secret",
                "apiKey": "",
                "apiSecret": "  ",
            },
        )
        self.assertEqual(response.status, 201)
        stored = await self.store.get("accounts", account["id"])
        credentials = Vault(KEY).decrypt(stored["credentials"])
        self.assertEqual(
            credentials,
            {
                "token": "new-user-token",
                "tokenSecret": "new-user-secret",
                "apiKey": "saved-consumer-key",
                "apiSecret": "saved-consumer-secret",
            },
        )
        self.assertNotIn("new-user-token", await response.text())
        self.assertEqual(self.send.await_count, 1)
        response = await self.client.post(
            "/api/accounts", json={"id": account["id"], "platform": "x"}
        )
        self.assertEqual(response.status, 201)
        self.assertEqual(
            Vault(KEY).decrypt((await self.store.get("accounts", account["id"]))["credentials"]),
            credentials,
        )

    async def test_connection_defaults_only_exposes_public_fields(self):
        for platform, credentials in (
            (
                "bluesky",
                {
                    "identifier": "tester.bsky.social",
                    "instance": "https://bsky.social",
                    "password": "private-test-password",
                },
            ),
            ("mastodon", {"instance": "https://mastodon.example", "token": "private-test-token"}),
            (
                "discord",
                {
                    "webhook": "https://discord.com/api/v10/webhooks/12345/private-test-token",
                    "threadId": "12345",
                },
            ),
        ):
            await self.store.put(
                "accounts",
                {
                    "id": "saved-" + platform,
                    "platform": platform,
                    "credentials": Vault(KEY).encrypt(credentials),
                },
            )
            response = await self.client.get(f"/api/accounts/saved-{platform}/connection")
            self.assertEqual(response.status, 200)
            defaults = await response.json()
            self.assertNotIn("private-test", str(defaults))
            self.assertIn("secret", defaults["savedFields"])
            self.assertTrue(set(defaults["values"]) <= {"handle", "instance"})
            if "instance" in credentials:
                self.assertEqual(defaults["values"]["instance"], credentials["instance"])
        self.send.assert_not_awaited()

    async def test_reconnect_invalid_identity_does_not_send_credentials(self):
        for payload in (
            {"id": "missing", "platform": "x"},
            {"id": "test-bluesky", "platform": "x"},
        ):
            response = await self.client.post("/api/accounts", json=payload)
            self.assertEqual(response.status, 400)
        self.send.assert_not_awaited()

    async def test_upload_alt_text_attach_and_reject_deletion(self):
        form = aiohttp.FormData()
        form.add_field("file", PNG, filename="dot.png", content_type="image/png")
        response = await self.client.post("/api/media", data=form)
        self.assertEqual(response.status, 201)
        media = await response.json()
        image_path = self.jobs.media_dir / (media["id"] + ".bin")
        self.assertEqual(image_path.read_bytes(), PNG)
        self.assertEqual(image_path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("sourceUrl", media)
        self.assertEqual(
            (await self.client.get("/api/media/" + media["id"])).content_type, "image/png"
        )
        self.assertEqual(
            (
                await self.client.put("/api/media/" + media["id"], json={"alt": "A single dot"})
            ).status,
            200,
        )
        self.assertEqual((await self.create_post(mediaIds=[media["id"]])).status, 201)
        self.assertEqual((await self.client.delete("/api/media/" + media["id"])).status, 400)
        state = await (await self.client.get("/api/state")).json()
        self.assertNotIn("data", state["media"][0])

    async def test_invalid_and_oversize_image_upload(self):
        for data in (b"<svg></svg>", b"\x89PNG\r\n\x1a\n" + b"0" * 1048576):
            form = aiohttp.FormData()
            form.add_field("file", data, filename="invalid.png", content_type="image/png")
            self.assertEqual((await self.client.post("/api/media", data=form)).status, 400)

    async def test_origin_and_hostname_guards(self):
        self.assertEqual(
            (
                await self.client.post(
                    "/api/demo", json={}, headers={"Origin": "https://evil.example"}
                )
            ).status,
            403,
        )
        self.assertEqual(
            (await self.client.get("/api/state", headers={"Host": "evil.example"})).status, 403
        )
        self.assertEqual(
            (await self.client.get("/api/state", headers={"Sec-Fetch-Site": "cross-site"})).status,
            403,
        )

    async def test_settings_timezone_validation_and_export(self):
        self.assertEqual(
            (
                await self.client.put(
                    "/api/settings", json={"name": "Home", "timezone": "Mars/Base"}
                )
            ).status,
            400,
        )
        self.assertEqual(
            (
                await self.client.put(
                    "/api/settings", json={"name": "Home", "timezone": "America/New_York"}
                )
            ).status,
            200,
        )
        exported = await (await self.client.get("/api/export")).json()
        self.assertEqual(exported["settings"]["name"], "Home")

    async def test_static_routes_and_security_headers(self):
        for route in ("/", "/app", "/app.js", "/styles.css"):
            response = await self.client.get(route)
            self.assertEqual(response.status, 200)
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        for logo in Path("web/logos").glob("*.svg"):
            response = await self.client.get("/logos/" + logo.name)
            self.assertEqual(response.status, 200, logo.name)
            self.assertEqual(response.content_type, "image/svg+xml", logo.name)
            self.assertEqual(await response.read(), logo.read_bytes())
        self.assertEqual((await self.client.get("/.env")).status, 404)
        self.assertEqual((await self.client.get("/lightpost/config.py")).status, 404)

    async def test_removed_demo_endpoint_and_hidden_sample_records(self):
        response = await self.client.post("/api/demo", json={})
        self.assertIn(response.status, (404, 405))
        await self.store.put(
            "accounts",
            {"id": "test-demo", "platform": "bluesky", "name": "Test sample", "demo": True},
        )
        await self.store.put(
            "posts", post("sample", accountIds=["test-demo"], demo=True, status="draft")
        )
        state = await (await self.client.get("/api/state")).json()
        self.assertNotIn("test-demo", [a["id"] for a in state["accounts"]])
        self.assertNotIn("sample", [p["id"] for p in state["posts"]])
        self.assertEqual((await self.create_post(accountIds=["test-demo"])).status, 400)

    async def test_portal_docs_are_served_and_cover_each_platform(self):
        response = await self.client.get("/guides.js")
        self.assertEqual(response.status, 200)
        content = await response.text()
        for platform in ("discord", "bluesky", "mastodon", "x", "instagram", "threads"):
            self.assertIn("id: '" + platform + "'", content)
        self.assertIn("Step ${index + 1}:", await (await self.client.get("/app.js")).text())
        for platform, count in (("instagram", 14), ("x", 4)):
            screenshots = list(Path(f"web/images/{platform}").glob("s*.png"))
            self.assertEqual(len(screenshots), count)
            for screenshot in screenshots:
                route = f"/images/{platform}/" + screenshot.name
                self.assertIn(route, content)
                response = await self.client.get(route)
                self.assertEqual(response.status, 200, route)
                self.assertEqual(response.content_type, "image/png", route)
                self.assertEqual(await response.read(), screenshot.read_bytes())

    async def test_password_login_logout_and_limit(self):
        self.config.password = "test-password-long-enough"
        self.assertEqual((await self.client.get("/api/state")).status, 401)
        self.assertEqual(
            (await self.client.post("/api/login", json={"password": "incorrect"})).status, 401
        )
        response = await self.client.post("/api/login", json={"password": self.config.password})
        self.assertEqual(response.status, 200)
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertEqual((await self.client.get("/api/state")).status, 200)
        await self.client.post("/api/logout", json={})
        self.assertEqual((await self.client.get("/api/state")).status, 401)
        for _ in range(10):
            response = await self.client.post("/api/login", json={"password": "wrong"})
        self.assertEqual(response.status, 429)


if __name__ == "__main__":
    unittest.main()
