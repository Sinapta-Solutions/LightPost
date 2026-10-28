import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from lightpost.app import clean_account
from lightpost.providers import (
    ProviderError,
    Providers,
    Transport,
    destination_post,
    validate_post,
)
from lightpost.security import Vault

KEY = "b2" * 32  # Test-only encryption key.
TOKEN = "TEST_ONLY_LINKEDIN_MEMBER_TOKEN"
URN = "urn:li:ugcPost:123456789"
JPEG = b"\xff\xd8\xfftest-image"


def post(**changes):
    return {"id": "test-post", "text": "Hello LinkedIn", "mediaIds": [], **changes}


def registration(
    asset="asset1", url="https://api.linkedin.com/mediaUpload/asset1?signature=test-only"
):
    return {
        "value": {
            "asset": "urn:li:digitalmediaAsset:" + asset,
            "uploadMechanism": {
                "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest": {"uploadUrl": url}
            },
        }
    }


class LinkedInTests(unittest.IsolatedAsyncioTestCase):
    def setup_provider(self, responses):
        self.vault = Vault(KEY)
        self.send = AsyncMock(side_effect=responses)
        self.provider = Providers(self.vault, self.send, pause=AsyncMock())
        self.account = {
            "id": "li",
            "platform": "linkedin",
            "name": "LinkedIn",
            "remoteId": "testMember",
            "credentials": self.vault.encrypt({"token": TOKEN}),
        }

    async def test_connection_verifies_member_without_publishing_or_exposing_token(self):
        self.setup_provider(
            [{"sub": "testMember", "name": "Test Member", "email": "unused@example.org"}]
        )
        account = await self.provider.connect({"platform": "linkedin", "secret": TOKEN})
        self.assertEqual(account["remoteId"], "testMember")
        self.assertEqual(account["handle"], "Test Member")
        self.assertEqual(self.vault.decrypt(account["credentials"]), {"token": TOKEN})
        self.assertNotIn(TOKEN, json.dumps(account))
        self.assertNotIn(TOKEN, json.dumps(clean_account(account)))
        self.assertNotIn("email", account)
        self.assertEqual(self.send.await_count, 1)
        self.assertEqual(self.send.call_args.args, ("GET", "https://api.linkedin.com/v2/userinfo"))

    async def test_bad_member_or_missing_identity_permissions_cannot_connect(self):
        self.setup_provider([{"sub": "bad/member"}, ProviderError("rejected", status=403)])
        with self.assertRaisesRegex(ValueError, "valid member identity"):
            await self.provider.connect({"platform": "linkedin", "secret": TOKEN})
        with self.assertRaises(ProviderError) as caught:
            await self.provider.connect({"platform": "linkedin", "secret": TOKEN})
        self.assertIn("openid, profile and w_member_social", str(caught.exception))
        self.assertNotIn(TOKEN, str(caught.exception))

    async def test_text_share_uses_verified_author_and_header_receipt(self):
        self.setup_provider([{"data": {}, "headers": {"x-restli-id": URN}}])
        result = await self.provider.publish(self.account, post(), [], AsyncMock())
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["remoteId"], URN)
        self.assertEqual(result["url"], "https://www.linkedin.com/feed/update/" + URN + "/")
        call = self.send.call_args
        self.assertEqual(call.args, ("POST", "https://api.linkedin.com/v2/ugcPosts"))
        self.assertTrue(call.kwargs["_receipt"])
        self.assertEqual(call.kwargs["headers"]["X-Restli-Protocol-Version"], "2.0.0")
        body = call.kwargs["json"]
        self.assertEqual(body["author"], "urn:li:person:testMember")
        self.assertEqual(
            body["specificContent"]["com.linkedin.ugc.ShareContent"]["shareMediaCategory"], "NONE"
        )
        self.assertNotIn(TOKEN, json.dumps(body))

    async def test_images_are_registered_uploaded_and_included_with_alt_text(self):
        self.setup_provider(
            [registration("first"), b"", registration("second"), b"", {"data": {"id": URN}}]
        )
        images = [
            {"bytes": JPEG, "mime": "image/jpeg", "alt": "A photo"},
            {"bytes": JPEG, "mime": "image/jpeg", "alt": "Another photo"},
        ]
        checkpoint = AsyncMock()
        result = await self.provider.publish(
            self.account, post(mediaIds=["first", "second"]), images, AsyncMock(), None, checkpoint
        )
        self.assertEqual(result["status"], "published")
        calls = self.send.call_args_list
        self.assertEqual([call.args[0] for call in calls], ["POST", "PUT", "POST", "PUT", "POST"])
        self.assertEqual(calls[1].kwargs["data"], JPEG)
        self.assertEqual(calls[1].kwargs["headers"]["Content-Type"], "image/jpeg")
        content = calls[-1].kwargs["json"]["specificContent"]["com.linkedin.ugc.ShareContent"]
        self.assertEqual(content["shareMediaCategory"], "IMAGE")
        self.assertEqual(
            [m["media"] for m in content["media"]],
            ["urn:li:digitalmediaAsset:first", "urn:li:digitalmediaAsset:second"],
        )
        self.assertEqual(content["media"][0]["description"]["text"], "A photo")
        self.assertEqual(checkpoint.call_args.args[0]["stage"], "publishing")

    async def test_upload_destination_cannot_receive_token_on_another_host(self):
        for url in (
            "https://attacker.example/upload",
            "https://api.linkedin.com.attacker.example/upload",
            "http://api.linkedin.com/upload",
            "https://user:pass@api.linkedin.com/upload",
            "https://127.0.0.1/upload",
        ):
            self.setup_provider([registration(url=url)])
            with self.assertRaises(ProviderError):
                await self.provider.publish(
                    self.account,
                    post(mediaIds=["image"]),
                    [{"bytes": JPEG, "mime": "image/jpeg"}],
                    AsyncMock(),
                )
            self.assertEqual(self.send.await_count, 1)

    async def test_missing_receipt_is_uncertain_and_never_automatically_reposts(self):
        self.setup_provider([{"data": {}, "headers": {}}])
        with self.assertRaises(ProviderError) as caught:
            await self.provider.publish(self.account, post(), [], AsyncMock())
        self.assertTrue(caught.exception.uncertain)
        self.assertEqual(self.send.await_count, 1)

    def test_content_options_and_platform_limit(self):
        account = {"id": "li", "platform": "linkedin", "name": "LinkedIn"}
        value = destination_post(
            account, post(mediaIds=["image"], contentOptions={"li": {"image": False}})
        )
        self.assertEqual(value["mediaIds"], [])
        validate_post(account, value)
        with self.assertRaisesRegex(ValueError, "3?000"):
            validate_post(account, post(text="a" * 3001))

    async def test_transport_retains_only_linkedin_receipt_header(self):
        class Content:
            async def iter_chunked(self, size):
                if False:
                    yield b""

        class Response:
            status = 201
            headers = {"x-restli-id": URN, "authorization": "never-return-this"}
            content = Content()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        transport = Transport.__new__(Transport)
        transport.session = SimpleNamespace(request=lambda *a, **kw: Response())
        result = await transport("POST", "https://api.linkedin.com/v2/ugcPosts", _receipt=True)
        self.assertEqual(result, {"data": {}, "headers": {"x-restli-id": URN}})
