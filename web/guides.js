// Public setup instructions only. Never place account credentials in this file.
export const guides = [
  {
    id: 'discord',
    titles: [
      'Create a webhook',
      'Choose your channel',
      'Connect in LightPost',
      'Add more channels',
    ],
    name: 'Discord',
    account: 'A server where you can manage webhooks',
    approval:
      'No developer app or app review. Creating a webhook requires Manage Webhooks permission on the server.',
    credentials: 'The incoming webhook URL for the channel. No bot token.',
    steps: [
      'Open Discord → Server Settings → Integrations → Webhooks → New Webhook.',
      'Choose the text channel, give the webhook a name, and copy its webhook URL.',
      'In LightPost → Accounts → Connect account → Discord, paste the URL and select Verify & connect.',
      'Create a separate webhook for each channel you want to post to. Select several destinations in the composer if needed.',
    ],
    limits:
      'Posts use Discord Components V2 with text and an image gallery in one card. Text up to 2,000 characters and four images imported from public URLs, up to 1 MB each. Discord loads gallery images directly from their original URLs, so keep those URLs available. Mentions do not ping users, roles or everyone. Use a regular text channel; an existing thread can be targeted with thread_id in the URL.',
    troubleshooting:
      'If verification fails, check that the webhook still exists and that the URL was copied in full. Treat the URL as a password. Recreate it if it leaks.',
    links: [
      [
        'Webhook setup',
        'https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks',
      ],
      ['Webhook API', 'https://docs.discord.com/developers/resources/webhook'],
    ],
  },
  {
    id: 'bluesky',
    titles: [
      'Open app passwords',
      'Create a LightPost password',
      'Enter your credentials',
      'Choose your home server',
      'Verify your account',
    ],
    name: 'Bluesky',
    account: 'Your own Bluesky account',
    approval: 'No developer application or app review for this app-password workflow.',
    credentials: 'Your handle and a Bluesky app password, not your normal password.',
    steps: [
      'Sign into Bluesky and open Settings → Privacy and security → App passwords. Settings labels may vary between clients.',
      'Create an app password named LightPost and copy it before closing the dialog.',
      'In LightPost → Accounts → Connect account → Bluesky, enter your handle and the app password.',
      'Leave Home server blank for accounts hosted on bsky.social. For a different host, enter your actual public HTTPS personal data server (PDS) address.',
      'Select Verify & connect. Repeat with the credentials for each additional account.',
    ],
    limits:
      'Text up to 300 graphemes and four local images, up to 1 MB each. The app refreshes its session as it posts.',
    troubleshooting:
      'Use an app password without adding spaces, and check the handle and home server. If the app password was revoked, create another and reconnect the same account.',
    links: [
      ['App passwords', 'https://bsky.app/settings/app-passwords'],
      ['Authentication reference', 'https://bsky.network/docs/api-directory/'],
    ],
  },
  {
    id: 'mastodon',
    titles: [
      'Create an application',
      'Set publishing permissions',
      'Copy your access token',
      'Connect in LightPost',
      'Add more accounts',
    ],
    name: 'Mastodon',
    account: 'Your own account on a public Mastodon instance',
    approval: 'No central app review. Your instance administrator can set additional policies.',
    credentials:
      'Instance URL and a personal application access token. Scopes: read:accounts, write:statuses, write:media.',
    steps: [
      'In your instance’s web interface, open Preferences → Development → New application.',
      'Name the application LightPost and enable read:accounts, write:statuses and write:media.',
      'Save the application and copy the access token shown for your account.',
      'In LightPost → Accounts → Connect account → Mastodon, enter the instance URL and access token.',
      'Select Verify & connect. Each account needs its own token, even on the same instance.',
    ],
    limits:
      'Public text posts, conservatively limited to 500 characters, and four images up to 1 MB each. Instance-specific restrictions still apply.',
    troubleshooting:
      'Use the instance’s base HTTPS URL, without a path or port. Missing write:media permission can allow text while rejecting image posts.',
    links: [
      ['Application and token setup', 'https://docs.joinmastodon.org/client/token/'],
      ['Posting permissions', 'https://docs.joinmastodon.org/methods/statuses/'],
    ],
  },
  {
    id: 'x',
    titles: [
      'Create your developer app',
      'Enable Read and Write',
      'Copy app credentials',
      'Generate user tokens',
      'Check API access and credits',
      'Connect in LightPost',
    ],
    name: 'X (Twitter)',
    account: 'Your own X (Twitter) account plus an X (Twitter) developer application',
    approval:
      'Complete X (Twitter)’s developer registration and app access requirements. API access and credits depend on your developer account; verification and publishing can incur charges.',
    credentials:
      'Consumer Key, Consumer Secret, Access Token and Access Token Secret from OAuth 1.0 Keys. The app needs OAuth 1.0a Read and Write access.',
    steps: [
      'Sign into the X (Twitter) Developer Console, register for developer access, and create an app.',
      'Configure user authentication with OAuth 1.0a and Read and Write permissions. Complete the app information required by the console.',
      'Open Keys and tokens. Save the Consumer Key and Consumer Secret from OAuth 1.0 Keys. The OAuth 2.0 Client Secret is a different credential.',
      'Generate or regenerate the Access Token and Access Token Secret after enabling write permissions. These must belong to the account you want to post from.',
      'Check your console’s current API access, credit balance and spending settings before publishing.',
      'In LightPost → Accounts → Connect account → X (Twitter), enter all four credentials and verify the connection.',
    ],
    limits:
      'Up to 280 weighted characters and four JPEG/PNG images, 1 MB each. Images upload directly and are attached as media IDs; their source URLs are never appended to the caption. The $0.015 post-create estimate excludes other API operations; posts containing a caption URL are listed at $0.20. Check current charges in the X (Twitter) Developer Console. An app-only bearer token cannot publish. Another account needs its own authorized user token pair; LightPost does not provide that OAuth consent flow.',
    troubleshooting:
      'If reads work but posting fails, verify write access and regenerate the user tokens after changing permissions. Check credits and account restrictions too.',
    links: [
      ['Developer Console', 'https://developer.x.com/'],
      [
        'API keys and secrets',
        'https://docs.x.com/fundamentals/authentication/oauth-1-0a/api-key-and-secret',
      ],
      ['Current pricing', 'https://docs.x.com/x-api/getting-started/pricing'],
    ],
  },
  {
    id: 'instagram',
    name: 'Instagram',
    account: 'An Instagram Creator or Business account',
    approval:
      'Use your own Instagram Creator or Business account and add it to your Meta app as an app-role/test account. Regular personal Instagram accounts cannot publish through this API.',
    credentials:
      'A long-lived Instagram Login user token with instagram_business_basic and instagram_business_content_publish. Not a Facebook Page token.',
    steps: [
      {
        title: 'Use a professional Instagram account',
        text: 'Use your own Creator or Business account. In Instagram settings, switch to a professional account if not already done.',
        images: [],
      },
      {
        title: 'Register as a Meta developer',
        text: 'and register as a Meta developer. You need to log in with your Facebook account.',
        link: {
          label: 'Meta developer registration',
          url: 'https://developers.facebook.com/async/registration/',
        },
        images: [],
      },
      {
        title: 'Set up Instagram in your Meta app',
        text: 'Create a Meta developer app, then add the Instagram API / Instagram Login use case and open its setup. For this own-account setup, use Standard Access and app roles. If the business portfolio screen offers Add later, you can choose it; this setup does not request access to other people’s accounts.',
        images: [],
      },
      {
        title: 'Invite your Instagram account as a tester',
        text: 'Open App roles → Roles → Add people. Choose Instagram Tester, enter your real Instagram username and send the invitation. Use your existing account, rather than creating a fake test user. Some dashboards offer Add account under Instagram → API setup with Instagram login → Generate access tokens.',
        images: [],
      },
      {
        title: 'Accept the tester invitation on Instagram',
        text: 'Sign into the Instagram account you invited. Open Settings → Website permissions → Apps and websites → Tester invites and accept your app’s invitation. Menu labels can vary between web and mobile. Sending the invitation alone is not enough.',
        images: [],
      },
      {
        title: 'Authorize publishing and generate a token',
        text: 'Return to Meta → Instagram → API setup with Instagram login. Connect your account and authorize instagram_business_basic and instagram_business_content_publish. Use Meta’s token setup or documented OAuth flow to obtain a user token and exchange it for a long-lived token. LightPost does not perform that initial consent or exchange. Keep the token private.',
        images: [],
      },
      {
        title: 'Connect your account in LightPost',
        text: 'Open LightPost → Accounts → Connect account → Instagram. Paste the long-lived Instagram user token and select Verify & connect. Use an Instagram Login token, not a Facebook Page token.',
        images: [],
      },
    ],
    limits:
      'One JPEG at a direct public HTTPS URL, up to 1 MB, with a caption up to 2,200 characters. Use Add Image in the composer. The URL must remain available until publishing finishes; your server can remain private. No Reels, Stories or carousels in this version.',
    troubleshooting:
      'Check account eligibility, app-role invitation acceptance, token type and scopes. Meta must be able to fetch the JPEG without a login or redirect. Reconnect expired or revoked tokens.',
    links: [
      [
        'Instagram Login setup',
        'https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/',
      ],
      [
        'Meta’s API examples',
        'https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api',
      ],
    ],
  },
  {
    id: 'threads',
    titles: [
      'Create your Meta app',
      'Add and authorize your own account',
      'Get a long-lived token',
      'Connect in LightPost',
    ],
    name: 'Threads',
    account: 'Your own Threads account',
    approval:
      'Use your own Threads account and add it as a tester or app-role user in your Meta app. An Instagram Business account is not required.',
    credentials: 'A long-lived Threads user token with threads_basic and threads_content_publish.',
    steps: [
      'Create a Meta developer app with the Threads API use case.',
      'Add your Threads account as a tester or app-role user, accept the invitation, and authorize the requested scopes.',
      'Use the Threads developer setup or documented OAuth flow to generate and exchange a user token for a long-lived token.',
      'In LightPost → Accounts → Connect account → Threads, paste the token and verify the connection.',
    ],
    limits:
      'Text up to 500 characters, or one public HTTPS JPEG up to 1 MB. Use Add Image for the image. LightPost waits for a container’s processing to finish before confirming publication.',
    troubleshooting:
      'Use a Threads token, not an Instagram token. Check tester authorization and both scopes. LightPost refreshes connected long-lived Meta tokens after seven days when used; expired or revoked tokens require reconnecting.',
    links: [
      ['Threads developer setup', 'https://developers.facebook.com/docs/threads/'],
      [
        'Meta’s publishing examples',
        'https://www.postman.com/meta/threads/request/ohuldvi/check-container-s-publishing-status',
      ],
    ],
  },
  {
    id: 'linkedin',
    name: 'LinkedIn',
    account: 'Your personal LinkedIn profile',
    approval:
      'Create a LinkedIn developer app. LinkedIn may ask you to associate and verify a LinkedIn Page for the app. Posting here uses your personal profile; organization Pages need separate permissions and are not supported.',
    credentials:
      'One member access token with openid, profile and w_member_social. Use LinkedIn’s official token generator; no client secret needs to be pasted into LightPost.',
    titles: [
      'Create an app',
      'Enable both products',
      'Generate a member token',
      'Connect your profile',
    ],
    steps: [
      'Open developer.linkedin.com, sign in, then open My apps → Create app. Complete the application details and Page verification if LinkedIn requests it.',
      'In Products, request Share on LinkedIn and Sign In with LinkedIn using OpenID Connect. Wait until both products are available and Auth lists openid, profile and w_member_social.',
      'From the signed-in developer portal, open Docs and tools → Token Generator. Choose your app, Member authorization code (3-legged), and the openid, profile and w_member_social scopes. Sign in as the member who will publish, approve access, then copy the access token.',
      'In LightPost → Accounts → Connect account → LinkedIn, paste the Member access token and choose Verify & connect. Repeat for another personal profile with that member’s own authorized token.',
    ],
    limits:
      'Public personal-profile posts with text up to 3,000 characters and up to four images, 1 MB each. Images upload directly to LinkedIn; a public image URL is not required. Links can be included in the text. Company Pages and videos are not supported.',
    troubleshooting:
      'If account verification fails, check openid and profile. If verification works but publishing fails, check w_member_social and the Share on LinkedIn product. Tokens expire or can be revoked; use the token generator again and Reconnect to replace the saved token. Self-service access tokens are not automatically refreshed by LightPost.',
    links: [
      ['Create a LinkedIn app', 'https://www.linkedin.com/developers/apps'],
      ['LinkedIn developer portal', 'https://developer.linkedin.com/'],
      [
        'Token setup instructions',
        'https://learn.microsoft.com/en-us/linkedin/shared/authentication/developer-portal-tools',
      ],
      [
        'Share on LinkedIn',
        'https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin',
      ],
    ],
  },
  {
    id: 'telegram',
    name: 'Telegram',
    account: 'A public or private Telegram channel you manage',
    approval:
      'Create a bot through Telegram’s official BotFather. No developer app registration or app review is needed for this channel-posting setup.',
    credentials:
      'Your bot token and the channel’s public @username or numeric channel ID beginning -100. Your personal Telegram login and phone number are not needed.',
    titles: [
      'Create a bot',
      'Grant channel posting permission',
      'Choose the destination',
      'Connect in LightPost',
      'Create a post',
    ],
    steps: [
      'Open the verified @BotFather account in Telegram. Send /newbot, follow its instructions and copy the bot token it gives you.',
      'Open your channel → Manage/Edit channel → Administrators → Add administrator. Add your new bot and enable Post Messages. Menu names vary between Telegram clients.',
      'For a public channel, use its @username. For a private channel, use its numeric ID beginning -100. An invite link such as t.me/+… cannot be used as a channel ID.',
      'In LightPost → Accounts → Connect account → Telegram, enter the channel and bot token, then choose Verify & connect. This checks the bot and its permissions without posting a test message. The same bot can connect to several channels separately.',
      'Select the channel in New post and publish now or schedule it. Text-only posts allow up to 4,096 characters; captions on a photo or album allow up to 1,024. Attach up to four JPEG or PNG images, 1 MB each. Emoji can count as two characters toward these limits.',
    ],
    limits:
      'Channel posts only. Text up to 4,096 characters, or up to four JPEG/PNG images with one caption up to 1,024 characters. Images upload directly; no public image URL is needed. Groups, direct messages, videos and custom formatting are not supported in this version.',
    troubleshooting:
      'If verification fails, check the bot token and channel ID, and make sure the bot is an administrator with Post Messages enabled. Reconnect if a token is revoked. Private-channel post links work only for channel members. If delivery is uncertain, check Telegram before retrying because a second attempt may create another post.',
    links: [
      ['Open BotFather', 'https://t.me/BotFather'],
      ['Official bot setup guide', 'https://core.telegram.org/bots/tutorial'],
      ['Telegram Bot API', 'https://core.telegram.org/bots/api'],
    ],
  },
  {
    id: 'facebook',
    name: 'Facebook Pages',
    account: 'A Facebook Page where you can create content',
    approval:
      'Use the Manage everything on your Page use case in a Meta developer app. For your own Page, check Standard Access and your app role. Advanced Access and App Review can be required for people outside the app’s roles. Personal profiles are not supported.',
    credentials:
      'Your numeric Page ID and that Page’s access token. If you already have both, use Connect Facebook Pages above. Keep your Instagram token in its existing account connection.',
    titles: [
      'Choose your Page',
      'Enable the Pages use case',
      'Authorize the permissions',
      'Get the Page token',
      'Connect and test',
    ],
    steps: [
      'Create a Facebook Page, or use one where you have full control or permission to create content. Your personal profile is not a Page.',
      'Open Meta for Developers and select your existing app, or create an app. Add the Manage everything on your Page use case. Add pages_manage_posts and its dependencies pages_read_engagement and pages_show_list where available in the app dashboard.',
      'Open Graph API Explorer, select the same Meta app, and generate a User Access Token requesting those Page permissions. During authorization, select the Facebook Page you want to manage. If you change permissions, generate a new token; adding them in the dashboard does not update an old token.',
      'In Graph API Explorer, run GET me/accounts?fields=id,name,access_token,tasks with the User token. Find your Page and copy its id and access_token. The token inside the Page entry is the Page access token. An empty data list can mean no Page is managed by this account, missing permissions, or that the Page was not selected during authorization.',
      'In LightPost → Accounts → Connect account → Facebook Pages, enter the Page ID and Page access token. Verify & connect checks the Page identity without publishing a test post. Then select the Page in New post to publish now or schedule text and up to four JPEG/PNG images, 1 MB each.',
    ],
    limits:
      'Page feed posts only: text up to the app’s 10,000-character limit, and up to four JPEG/PNG images. Images upload directly from this server; public image URLs are not required. Videos, Reels, Stories, groups and personal-profile posting are not included.',
    troubleshooting:
      'A connection verifies Page identity; publishing still needs the correct Page permissions. If Meta rejects a post, check the token’s granted permissions and your Page content access. For reliable scheduling, derive the Page token from a long-lived User token and check expiration in Meta’s Access Token Debugger. LightPost does not extend Facebook tokens automatically. Tokens can expire or be revoked; use Reconnect to replace them. Check the Page before retrying an uncertain delivery.',
    links: [
      ['Meta developer apps', 'https://developers.facebook.com/apps/'],
      ['Graph API Explorer', 'https://developers.facebook.com/tools/explorer/'],
      ['Access Token Debugger', 'https://developers.facebook.com/tools/debug/accesstoken/'],
      [
        'Page access-token example',
        'https://www.postman.com/meta/facebook/request/bqfxwbp/get-access-tokens-of-pages-you-manage',
      ],
      ['Facebook Pages publishing', 'https://developers.facebook.com/docs/pages-api/posts/'],
    ],
  },
];
