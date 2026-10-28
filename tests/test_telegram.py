import json
import unittest
from unittest.mock import AsyncMock

from lightpost.app import clean_account
from lightpost.providers import Providers, ProviderError, destination_post, validate_post
from lightpost.security import Vault
import test_python as original

KEY = "c3" * 32  # Test-only key; no real Telegram account is used.
TOKEN = "123456789:" + "TEST_ONLY_" * 4
BOT_ID = 123456789
CHAT_ID = -1001234567890
JPEG = b"\xff\xd8\xfftest-image"


def ok(result):
    return {"ok": True, "result": result}


def connection(*, username="demo_channel", **member_changes):
    return [
        ok({"id": BOT_ID, "is_bot": True, "username": "test_bot"}),
        ok({"id": CHAT_ID, "type": "channel", "username": username, "title": "Demo channel"}),
        ok(
            {
                "user": {"id": BOT_ID},
                "status": "administrator",
                "can_post_messages": True,
                **member_changes,
            }
        ),
    ]


def message(id=42, *, username="demo_channel", chat_id=CHAT_ID):
    return {"message_id": id, "chat": {"id": chat_id, "type": "channel", "username": username}}


def post(**changes):
    return {"id": "test-post", "text": "Hello Telegram", "mediaIds": [], **changes}


def fields(form):
    return {options["name"]: value for options, _, value in form._fields}


class TelegramProviderTests(unittest.IsolatedAsyncioTestCase):
    def setup_provider(self, responses):
        self.vault = Vault(KEY)
        self.send = AsyncMock(side_effect=responses)
        self.provider = Providers(self.vault, self.send)
        self.account = {
            "id": "tg",
            "platform": "telegram",
            "name": "Telegram",
            "remoteId": str(CHAT_ID),
            "credentials": self.vault.encrypt(
                {"token": TOKEN, "chatId": str(CHAT_ID), "botId": BOT_ID}
            ),
        }

    async def test_connection_only_reads_bot_channel_and_posting_permissions(self):
        self.setup_provider(connection())
        account = await self.provider.connect(
            {"platform": "telegram", "secret": TOKEN, "chatId": "@demo_channel"}
        )
        self.assertEqual(account["remoteId"], str(CHAT_ID))
        self.assertEqual(account["handle"], "@demo_channel")
        credentials = self.vault.decrypt(account["credentials"])
        self.assertEqual(credentials["chatId"], str(CHAT_ID))
        self.assertEqual(credentials["botId"], BOT_ID)
        self.assertEqual([c.args[0] for c in self.send.call_args_list], ["GET"] * 3)
        self.assertEqual(
            [c.args[1].rsplit("/", 1)[-1] for c in self.send.call_args_list],
            ["getMe", "getChat", "getChatMember"],
        )
        self.assertNotIn(TOKEN, json.dumps(account))
        self.assertNotIn(TOKEN, json.dumps(clean_account(account)))

    async def test_private_channel_uses_numeric_id_and_readable_title(self):
        self.setup_provider(connection(username=""))
        account = await self.provider.connect(
            {"platform": "telegram", "secret": TOKEN, "chatId": str(CHAT_ID)}
        )
        self.assertEqual(account["handle"], "Demo channel")
        self.assertEqual(account["remoteId"], str(CHAT_ID))

    async def test_no_post_permission_wrong_bot_or_wrong_chat_type_is_rejected(self):
        for member_changes in (
            {"can_post_messages": False},
            {"status": "member"},
            {"user": {"id": BOT_ID + 1}},
        ):
            self.setup_provider(connection(**member_changes))
            with self.assertRaisesRegex(ValueError, "administrator"):
                await self.provider.connect(
                    {"platform": "telegram", "secret": TOKEN, "chatId": "@demo_channel"}
                )
        responses = connection()
        responses[1]["result"]["type"] = "supergroup"
        self.setup_provider(responses)
        with self.assertRaisesRegex(ValueError, "channel"):
            await self.provider.connect(
                {"platform": "telegram", "secret": TOKEN, "chatId": "@demo_channel"}
            )
        self.assertEqual(self.send.await_count, 2)

    async def test_invalid_token_or_invite_link_is_rejected_before_network_access(self):
        for token, channel in (
            (TOKEN + "/injected", "@demo_channel"),
            (TOKEN, "https://t.me/+invite"),
            (TOKEN, "private"),
        ):
            self.setup_provider([])
            with self.assertRaises(ValueError):
                await self.provider.connect(
                    {"platform": "telegram", "secret": token, "chatId": channel}
                )
            self.send.assert_not_awaited()

    async def test_plain_text_sends_once_without_formatting_and_returns_post_link(self):
        self.setup_provider([ok(message())])
        result = await self.provider.publish(
            self.account, post(text="*Plain* <text> https://example.org"), [], AsyncMock()
        )
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["url"], "https://t.me/demo_channel/42")
        self.assertEqual(self.send.await_count, 1)
        self.assertTrue(self.send.call_args.args[1].endswith("/sendMessage"))
        self.assertEqual(
            self.send.call_args.kwargs["json"],
            {"chat_id": str(CHAT_ID), "text": "*Plain* <text> https://example.org"},
        )
        self.assertNotIn(TOKEN, json.dumps(result))

    async def test_single_photo_uploads_bytes_with_one_caption_and_private_link(self):
        self.setup_provider([ok(message(username=""))])
        image = {"bytes": JPEG, "mime": "image/jpeg", "name": "test.jpg"}
        result = await self.provider.publish(
            self.account, post(mediaIds=["photo"]), [image], AsyncMock()
        )
        self.assertTrue(self.send.call_args.args[1].endswith("/sendPhoto"))
        data = fields(self.send.call_args.kwargs["data"])
        self.assertEqual(data["photo"], JPEG)
        self.assertEqual(data["caption"], "Hello Telegram")
        self.assertEqual(result["url"], "https://t.me/c/1234567890/42")

    async def test_album_uploads_once_with_caption_only_on_first_photo(self):
        self.setup_provider([ok([message(42), message(43), message(44)])])
        images = [{"bytes": JPEG, "mime": "image/jpeg"}] * 3
        result = await self.provider.publish(
            self.account, post(mediaIds=["a", "b", "c"]), images, AsyncMock()
        )
        self.assertEqual(self.send.await_count, 1)
        self.assertTrue(self.send.call_args.args[1].endswith("/sendMediaGroup"))
        data = fields(self.send.call_args.kwargs["data"])
        media = json.loads(data["media"])
        self.assertEqual(
            [m["media"] for m in media], ["attach://image0", "attach://image1", "attach://image2"]
        )
        self.assertEqual(media[0]["caption"], "Hello Telegram")
        self.assertTrue(all("caption" not in item for item in media[1:]))
        self.assertEqual(result["messageIds"], [42, 43, 44])
        self.assertEqual(data["image0"], JPEG)

    async def test_image_only_omits_caption_and_disabled_images_use_text_limit(self):
        self.setup_provider([ok(message())])
        value = destination_post(
            self.account, post(mediaIds=["a"], contentOptions={"tg": {"text": False}})
        )
        await self.provider.publish(
            self.account, value, [{"bytes": JPEG, "mime": "image/jpeg"}], AsyncMock()
        )
        self.assertNotIn("caption", fields(self.send.call_args.kwargs["data"]))
        value = destination_post(
            self.account,
            post(text="a" * 2000, mediaIds=["a"], contentOptions={"tg": {"image": False}}),
        )
        validate_post(self.account, value)
        self.assertEqual(value["mediaIds"], [])

    def test_text_and_photo_limits_include_emoji(self):
        account = {"platform": "telegram", "name": "Telegram"}
        validate_post(account, post(text="a" * 4096))
        validate_post(account, post(text="a" * 1024, mediaIds=["a"]))
        for value in (
            post(text="a" * 4097),
            post(text="a" * 1025, mediaIds=["a"]),
            post(text="😀" * 513, mediaIds=["a"]),
        ):
            with self.assertRaises(ValueError):
                validate_post(account, value)

    async def test_errors_never_echo_token_or_telegram_description_and_never_auto_retry(self):
        for response in (
            {"ok": False, "error_code": 403, "description": TOKEN},
            ProviderError(TOKEN, status=401),
            ProviderError(TOKEN, uncertain=True),
            {"ok": False, "error_code": 429, "description": TOKEN},
        ):
            self.setup_provider([response])
            with self.assertRaises(ProviderError) as caught:
                await self.provider.publish(self.account, post(), [], AsyncMock())
            self.assertNotIn(TOKEN, str(caught.exception))
            self.assertEqual(self.send.await_count, 1)

    async def test_missing_partial_or_wrong_channel_receipt_is_uncertain(self):
        for response in (ok({}), ok(message(chat_id=-1009999999)), ok([])):
            self.setup_provider([response])
            with self.assertRaises(ProviderError) as caught:
                await self.provider.publish(self.account, post(), [], AsyncMock())
            self.assertTrue(caught.exception.uncertain)
        self.setup_provider([ok([message()])])
        with self.assertRaises(ProviderError) as caught:
            await self.provider.publish(
                self.account,
                post(mediaIds=["a", "b"]),
                [{"bytes": JPEG, "mime": "image/jpeg"}] * 2,
                AsyncMock(),
            )
        self.assertTrue(caught.exception.uncertain)

    async def test_unsupported_images_or_too_many_images_never_publish(self):
        for images in (
            [{"bytes": JPEG, "mime": "image/webp"}],
            [{"bytes": JPEG, "mime": "image/jpeg"}] * 5,
        ):
            self.setup_provider([])
            with self.assertRaises(ValueError):
                await self.provider.publish(
                    self.account, post(mediaIds=["image"]), images, AsyncMock()
                )
            self.send.assert_not_awaited()

    async def test_demo_delivery_does_not_call_telegram(self):
        self.setup_provider([])
        result = await self.provider.publish(
            {**self.account, "demo": True}, post(), [], AsyncMock()
        )
        self.assertEqual(result["status"], "simulated")
        self.send.assert_not_awaited()


class TelegramApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = original.ApiTests.asyncSetUp
    asyncTearDown = original.ApiTests.asyncTearDown
    create_post = original.ApiTests.create_post

    async def test_connect_reconnect_duplicate_guard_and_private_export(self):
        self.send.side_effect = connection() + connection() + connection()
        payload = {"platform": "telegram", "secret": TOKEN, "chatId": "@demo_channel"}
        response = await self.client.post("/api/accounts", json=payload)
        self.assertEqual(response.status, 201)
        account = await response.json()
        defaults = await (await self.client.get(f"/api/accounts/{account['id']}/connection")).json()
        self.assertEqual(defaults["values"], {"chatId": str(CHAT_ID)})
        self.assertEqual(set(defaults["savedFields"]), {"secret", "chatId"})
        response = await self.client.post(
            "/api/accounts", json={"id": account["id"], "platform": "telegram"}
        )
        self.assertEqual(response.status, 201)
        response = await self.client.post("/api/accounts", json=payload)
        self.assertEqual(response.status, 400)
        for endpoint in ("/api/state", "/api/export"):
            self.assertNotIn(TOKEN, await (await self.client.get(endpoint)).text())
        response = await self.create_post(
            status="scheduled", scheduledAt=original.future(), accountIds=[account["id"]]
        )
        self.assertEqual(response.status, 201)
        response = await self.create_post(status="now", accountIds=[account["id"]], text="a" * 4097)
        self.assertEqual(response.status, 400)
