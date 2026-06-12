from __future__ import annotations

import logging
import urllib.request
import urllib.error
import urllib.parse
import json

logger = logging.getLogger(__name__)


def send_space_message(webhook_url: str, text: str) -> bool:
    """POST a text message to a Google Chat space via Incoming Webhook."""
    if not webhook_url or not text:
        return False
    payload = json.dumps({"text": text}).encode()
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status < 300:
                return True
            logger.warning("[google_chat] space webhook returned HTTP %s", resp.status)
            return False
    except urllib.error.HTTPError as e:
        logger.error("[google_chat] space webhook HTTP error %s: %s", e.code, e.reason)
        return False
    except Exception as e:
        logger.error("[google_chat] space webhook error: %s", e)
        return False


def send_dm(bot_token: str, user_email: str, text: str) -> bool:
    """Send a DM to a user via Google Chat Bot API using a service account token.

    The bot_token must be a valid OAuth2 access token for a service account
    that has been added to the target user's Google Chat DM space.
    Requires the Chat API scope: https://www.googleapis.com/auth/chat.messages.create
    """
    if not bot_token or not user_email or not text:
        return False

    # First, find or create a DM space with the user
    find_url = "https://chat.googleapis.com/v1/spaces:findDirectMessage"
    params = urllib.parse.urlencode({"name": f"users/{user_email}"})
    find_req = urllib.request.Request(
        f"{find_url}?{params}",
        headers={
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(find_req, timeout=10) as resp:
            space_data = json.loads(resp.read())
        space_name = space_data.get("name", "")
    except Exception as e:
        logger.error("[google_chat] findDirectMessage for %s failed: %s", user_email, e)
        return False

    if not space_name:
        logger.warning("[google_chat] no DM space found for %s", user_email)
        return False

    # Send message to the DM space
    msg_url = f"https://chat.googleapis.com/v1/{space_name}/messages"
    msg_payload = json.dumps({"text": text}).encode()
    msg_req = urllib.request.Request(
        msg_url,
        data=msg_payload,
        headers={
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(msg_req, timeout=10) as resp:
            if resp.status < 300:
                return True
            logger.warning("[google_chat] DM to %s returned HTTP %s", user_email, resp.status)
            return False
    except urllib.error.HTTPError as e:
        logger.error("[google_chat] DM to %s HTTP error %s: %s", user_email, e.code, e.reason)
        return False
    except Exception as e:
        logger.error("[google_chat] DM to %s error: %s", user_email, e)
        return False
