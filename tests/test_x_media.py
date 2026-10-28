import base64
import unittest
from unittest.mock import AsyncMock

from lightpost.jobs import PostingCancelled
from lightpost.providers import ProviderError, Providers, destination_post
from lightpost.security import Vault
from test_python import KEY, PNG, post


class XMediaTests(unittest.IsolatedAsyncioTestCase):
    def setup_provider(self, responses):
        vault = Vault(KEY)
        send = AsyncMock(side_effect=responses)
        providers = Providers(vault, send, pause=AsyncMock())
        account = {
            "id": "x",
            "name": "X (Twitter)",
            "platform": "x",
            "credentials": vault.encrypt(
                {
                    "apiKey": "test-key",
                    "apiSecret": "test-secret",
                    "token": "private-test-token",
                    "tokenSecret": "test-token-secret",
                }
            ),
        }
        return providers, send, account

    def image(self):
        return {
            "bytes": PNG,
            "mime": "image/png",
            "name": "test.png",
            "sourceUrl": "https://example.org/private-source.png",
        }

    async def test_four_images_attach_ids_without_source_links(self):
        providers, send, account = self.setup_provider(
            [*[{"data": {"id": str(i)}} for i in range(1, 5)], {"data": {"id": "99"}}]
        )
        checkpoint = AsyncMock()
        value = post(mediaIds=["1", "2", "3", "4"])
        result = await providers.publish(
            account, value, [self.image()] * 4, AsyncMock(), checkpoint=checkpoint
        )
        self.assertEqual(result["status"], "published")
        self.assertEqual(send.await_count, 5)
        for call in send.call_args_list[:-1]:
            self.assertEqual(call.args, ("POST", "https://api.x.com/2/media/upload"))
            self.assertEqual(
                call.kwargs["json"],
                {"media": base64.b64encode(PNG).decode(), "media_category": "tweet_image"},
            )
            self.assertTrue(call.kwargs["headers"]["Authorization"].startswith("OAuth "))
        self.assertEqual(
            send.call_args.kwargs["json"],
            {"text": value["text"], "media": {"media_ids": ["1", "2", "3", "4"]}},
        )
        self.assertNotIn("sourceUrl", str(send.call_args_list))
        self.assertNotIn("private-source", str(send.call_args_list))
        self.assertEqual(checkpoint.call_args.args[0]["stage"], "publishing")

    async def test_image_only_and_text_only(self):
        providers, send, account = self.setup_provider(
            [{"data": {"id": "1"}}, {"data": {"id": "99"}}]
        )
        await providers.publish(account, post(text="", mediaIds=["1"]), [self.image()], AsyncMock())
        self.assertEqual(send.call_args.kwargs["json"], {"media": {"media_ids": ["1"]}})
        value = destination_post(
            account, post(mediaIds=["1"], contentOptions={"x": {"image": False}})
        )
        self.assertEqual(value["mediaIds"], [])
        send.reset_mock(side_effect=True)
        send.return_value = {"data": {"id": "100"}}
        await providers.publish(account, value, [], AsyncMock())
        send.assert_awaited_once()
        self.assertEqual(send.call_args.kwargs["json"], {"text": value["text"]})

    async def test_caption_link_blocked_before_upload(self):
        providers, send, account = self.setup_provider([])
        with self.assertRaisesRegex(ValueError, "Links are disabled"):
            await providers.publish(
                account,
                post(text="Look https://example.org", mediaIds=["1"]),
                [self.image()],
                AsyncMock(),
            )
        send.assert_not_awaited()

    async def test_upload_errors_never_fall_back_to_text_or_echo_secrets(self):
        for response in (
            ProviderError("private-test-token", status=403),
            ProviderError("private-test-token", status=503, uncertain=True),
            {},
            {"data": {"id": "bad"}},
        ):
            providers, send, account = self.setup_provider([response])
            with self.assertRaises(ProviderError) as caught:
                await providers.publish(account, post(mediaIds=["1"]), [self.image()], AsyncMock())
            self.assertFalse(caught.exception.uncertain)
            self.assertNotIn("private-test-token", str(caught.exception))
            self.assertEqual(send.await_count, 1)

    async def test_waits_for_image_processing_before_post(self):
        providers, send, account = self.setup_provider(
            [
                {
                    "data": {
                        "id": "1",
                        "processing_info": {"state": "pending", "check_after_secs": 3},
                    }
                },
                {"data": {"processing_info": {"state": "succeeded"}}},
                {"data": {"id": "99"}},
            ]
        )
        await providers.publish(account, post(mediaIds=["1"]), [self.image()], AsyncMock())
        providers.pause.assert_awaited_once_with(3)
        self.assertEqual(send.call_args_list[1].args[0], "GET")
        self.assertEqual(send.call_args_list[2].args[1], "https://api.x.com/2/tweets")

    async def test_cancel_after_upload_prevents_post(self):
        providers, send, account = self.setup_provider([{"data": {"id": "1"}}])
        checkpoint = AsyncMock(side_effect=[None, PostingCancelled()])
        with self.assertRaises(PostingCancelled):
            await providers.publish(
                account, post(mediaIds=["1"]), [self.image()], AsyncMock(), checkpoint=checkpoint
            )
        self.assertEqual(send.await_count, 1)

    async def test_bad_publish_receipt_is_uncertain_and_not_retried(self):
        providers, send, account = self.setup_provider([{"data": {"id": "1"}}, {}])
        with self.assertRaises(ProviderError) as caught:
            await providers.publish(account, post(mediaIds=["1"]), [self.image()], AsyncMock())
        self.assertTrue(caught.exception.uncertain)
        self.assertEqual(send.await_count, 2)

    async def test_invalid_images_rejected_before_upload(self):
        providers, send, account = self.setup_provider([])
        for images in ([self.image()] * 5, [{**self.image(), "mime": "image/gif"}]):
            with self.assertRaises(ValueError):
                await providers.publish(account, post(mediaIds=["1"]), images, AsyncMock())
        send.assert_not_awaited()
