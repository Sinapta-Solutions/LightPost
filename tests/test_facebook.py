import json
import unittest
from unittest.mock import AsyncMock

from lightpost.app import clean_account
from lightpost.jobs import PostingCancelled
from lightpost.providers import (
    Providers,
    ProviderError,
    destination_post,
    platform_error,
    validate_post,
)
from lightpost.security import Vault
import test_python as original

KEY = "d4" * 32  # Test-only key; all Facebook calls below are mocked.
TOKEN = "PRIVATE_TEST_ONLY_FACEBOOK_PAGE_TOKEN"
PAGE_ID = "1234567890"
POST_ID = PAGE_ID + "_42"
JPEG = b"\xff\xd8\xfftest-image"


def post(**changes):
    return {"id": "test-post", "text": "Hello Facebook", "mediaIds": [], **changes}


def identity(**changes):
    return {"id": PAGE_ID, "name": "Demo Page", "category": "Brand", **changes}


def fields(form):
    return {options["name"]: value for options, _, value in form._fields}


class FacebookProviderTests(unittest.IsolatedAsyncioTestCase):
    def setup_provider(self, responses):
        self.vault = Vault(KEY)
        self.send = AsyncMock(side_effect=responses)
        self.provider = Providers(self.vault, self.send)
        self.account = {
            "id": "fb",
            "platform": "facebook",
            "name": "Facebook Pages",
            "remoteId": PAGE_ID,
            "credentials": self.vault.encrypt({"token": TOKEN, "pageId": PAGE_ID}),
        }

    async def test_connection_reads_page_identity_without_publishing(self):
        self.setup_provider([identity()])
        account = await self.provider.connect(
            {"platform": "facebook", "secret": TOKEN, "pageId": PAGE_ID}
        )
        self.assertEqual(account["remoteId"], PAGE_ID)
        self.assertEqual(account["handle"], "Demo Page")
        self.assertEqual(
            self.vault.decrypt(account["credentials"]), {"token": TOKEN, "pageId": PAGE_ID}
        )
        self.assertNotIn(TOKEN, json.dumps(account))
        self.assertNotIn(TOKEN, json.dumps(clean_account(account)))
        self.assertEqual(self.send.await_count, 1)
        self.assertEqual(self.send.call_args.args[0], "GET")
        self.assertTrue(self.send.call_args.args[1].endswith("/me"))
        self.assertEqual(self.send.call_args.kwargs["params"], {"fields": "id,name,category"})

    async def test_wrong_page_user_token_and_invalid_page_id_cannot_connect(self):
        for response in (identity(id="9999999999"), {"id": PAGE_ID, "name": "Personal profile"}):
            self.setup_provider([response])
            with self.assertRaisesRegex(ValueError, "Page"):
                await self.provider.connect(
                    {"platform": "facebook", "secret": TOKEN, "pageId": PAGE_ID}
                )
        self.setup_provider([])
        with self.assertRaises(ValueError):
            await self.provider.connect(
                {"platform": "facebook", "secret": TOKEN, "pageId": "https://facebook.com/example"}
            )
        self.send.assert_not_awaited()

    async def test_text_post_uses_page_endpoint_and_publication_receipt(self):
        self.setup_provider([{"id": POST_ID}, {"is_published": True}])
        checkpoint = AsyncMock()
        result = await self.provider.publish(
            self.account, post(), [], AsyncMock(), None, checkpoint
        )
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["url"], f"https://www.facebook.com/{PAGE_ID}/posts/42")
        call = self.send.call_args_list[0]
        self.assertEqual(call.args[0], "POST")
        self.assertTrue(call.args[1].endswith(f"/{PAGE_ID}/feed"))
        self.assertEqual(call.kwargs["data"], {"message": "Hello Facebook", "published": "true"})
        self.assertNotIn(TOKEN, json.dumps(call.kwargs["data"]))
        self.assertNotIn(TOKEN, json.dumps(result))
        self.assertEqual(checkpoint.call_args.args[0]["stage"], "publishing")

    async def test_photo_uploads_are_unpublished_then_attached_to_one_feed_post(self):
        self.setup_provider(
            [
                {"id": "101"},
                {"id": "102"},
                {"id": "103"},
                {"id": "104"},
                {"id": POST_ID},
                {"is_published": True},
            ]
        )
        images = [{"bytes": JPEG, "mime": "image/jpeg"}] * 4
        result = await self.provider.publish(
            self.account,
            post(mediaIds=["a", "b", "c", "d"]),
            images,
            AsyncMock(),
            None,
            AsyncMock(),
        )
        self.assertEqual(result["status"], "published")
        calls = self.send.call_args_list
        self.assertTrue(all(c.args[1].endswith("/photos") for c in calls[:4]))
        self.assertTrue(calls[4].args[1].endswith("/feed"))
        for call in calls[:4]:
            data = fields(call.kwargs["data"])
            self.assertEqual(data["published"], "false")
            self.assertEqual(data["source"], JPEG)
            self.assertNotIn("url", data)
        body = calls[4].kwargs["data"]
        self.assertEqual(
            json.loads(body["attached_media"]), [{"media_fbid": str(i)} for i in range(101, 105)]
        )
        self.assertEqual(body["message"], "Hello Facebook")
        self.assertEqual(sum(c.args[0] == "POST" and c.args[1].endswith("/feed") for c in calls), 1)

    async def test_retry_reuses_prepared_photo_ids(self):
        self.setup_provider([{"id": "102"}, {"id": POST_ID}, {"is_published": True}])
        value = post(mediaIds=["a", "b"])
        previous = {"photoIds": ["101"], "photoMediaIds": ["a", "b"]}
        await self.provider.publish(
            self.account,
            value,
            [{"bytes": JPEG, "mime": "image/jpeg"}] * 2,
            AsyncMock(),
            previous,
            AsyncMock(),
        )
        self.assertEqual(sum(c.args[1].endswith("/photos") for c in self.send.call_args_list), 1)
        body = self.send.call_args_list[1].kwargs["data"]
        self.assertEqual(
            json.loads(body["attached_media"]), [{"media_fbid": "101"}, {"media_fbid": "102"}]
        )

    async def test_known_unconfirmed_post_is_checked_without_republishing(self):
        self.setup_provider([{"id": POST_ID}, {"is_published": False}, {"is_published": True}])
        uncertain = await self.provider.publish(self.account, post(), [], AsyncMock())
        self.assertEqual(uncertain["status"], "uncertain")
        self.assertEqual(uncertain["remoteId"], POST_ID)
        result = await self.provider.publish(self.account, post(), [], AsyncMock(), uncertain)
        self.assertEqual(result["status"], "published")
        self.assertEqual(sum(c.args[0] == "POST" for c in self.send.call_args_list), 1)

    async def test_post_read_failure_does_not_undo_successful_publish_receipt(self):
        self.setup_provider([{"id": POST_ID}, ProviderError("read unavailable", status=403)])
        result = await self.provider.publish(self.account, post(), [], AsyncMock())
        self.assertEqual(result["status"], "published")

    async def test_permission_and_token_errors_are_actionable_and_private(self):
        for code, expected in ((190, "expired"), (200, "pages_manage_posts")):
            error = platform_error(
                400,
                "graph.facebook.com",
                json.dumps({"error": {"code": code, "message": TOKEN}}).encode(),
            )
            self.setup_provider([error])
            with self.assertRaises(ProviderError) as caught:
                await self.provider.publish(self.account, post(), [], AsyncMock())
            self.assertIn(expected, str(caught.exception))
            self.assertNotIn(TOKEN, str(caught.exception))
            self.assertFalse(caught.exception.uncertain)
            self.assertEqual(self.send.await_count, 1)

    async def test_unknown_or_missing_publication_receipt_is_uncertain_without_auto_retry(self):
        for response in (
            {},
            {"id": "9999999999_42"},
            ProviderError(TOKEN, uncertain=True),
            ProviderError(TOKEN, status=400),
        ):
            self.setup_provider([response])
            with self.assertRaises(ProviderError) as caught:
                await self.provider.publish(self.account, post(), [], AsyncMock())
            self.assertTrue(caught.exception.uncertain)
            self.assertNotIn(TOKEN, str(caught.exception))
            self.assertEqual(self.send.await_count, 1)

    async def test_photo_preparation_failure_does_not_send_feed_post(self):
        self.setup_provider([ProviderError(TOKEN, uncertain=True, status=500)])
        with self.assertRaises(ProviderError) as caught:
            await self.provider.publish(
                self.account,
                post(mediaIds=["a"]),
                [{"bytes": JPEG, "mime": "image/jpeg"}],
                AsyncMock(),
            )
        self.assertFalse(caught.exception.uncertain)
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertEqual(self.send.await_count, 1)
        self.assertTrue(self.send.call_args.args[1].endswith("/photos"))

    async def test_cancellation_checkpoint_stops_before_publication(self):
        self.setup_provider([])
        with self.assertRaises(PostingCancelled):
            await self.provider.publish(
                self.account, post(), [], AsyncMock(), None, AsyncMock(side_effect=PostingCancelled)
            )
        self.send.assert_not_awaited()

    async def test_demo_delivery_does_not_publish(self):
        self.setup_provider([])
        result = await self.provider.publish(
            {**self.account, "demo": True}, post(), [], AsyncMock()
        )
        self.assertEqual(result["status"], "simulated")
        self.send.assert_not_awaited()

    def test_image_options_and_app_character_limit(self):
        account = {"id": "fb", "platform": "facebook", "name": "Facebook Pages"}
        value = destination_post(
            account, post(mediaIds=["a"], contentOptions={"fb": {"image": False}})
        )
        self.assertEqual(value["mediaIds"], [])
        validate_post(account, post(text="a" * 10000))
        with self.assertRaises(ValueError):
            validate_post(account, post(text="a" * 10001))


class FacebookApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = original.ApiTests.asyncSetUp
    asyncTearDown = original.ApiTests.asyncTearDown
    create_post = original.ApiTests.create_post

    async def test_connect_reconnect_scheduling_and_private_export(self):
        self.send.side_effect = [identity(), identity(), identity(), identity(id="9999999999")]
        payload = {"platform": "facebook", "secret": TOKEN, "pageId": PAGE_ID}
        response = await self.client.post("/api/accounts", json=payload)
        self.assertEqual(response.status, 201)
        account = await response.json()
        self.assertNotIn("paused", account)
        defaults = await (await self.client.get(f"/api/accounts/{account['id']}/connection")).json()
        self.assertEqual(defaults["values"], {"pageId": PAGE_ID})
        self.assertEqual(set(defaults["savedFields"]), {"pageId", "secret"})
        response = await self.client.post(
            "/api/accounts", json={"id": account["id"], "platform": "facebook"}
        )
        self.assertEqual(response.status, 201)
        self.assertEqual((await self.client.post("/api/accounts", json=payload)).status, 400)
        response = await self.client.post(
            "/api/accounts", json={**payload, "id": account["id"], "pageId": "9999999999"}
        )
        self.assertEqual(response.status, 400)
        for endpoint in ("/api/state", "/api/export"):
            self.assertNotIn(TOKEN, await (await self.client.get(endpoint)).text())
        response = await self.create_post(
            status="scheduled", scheduledAt=original.future(), accountIds=[account["id"]]
        )
        self.assertEqual(response.status, 201)
