import os
import json
import random
import requests

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]

# NEW = SOURCE CHANNEL
# OLD = DESTINATION CHANNEL
NEW_CHANNEL_ID = str(os.environ["NEW_CHANNEL_ID"])
OLD_CHANNEL_ID = str(os.environ["OLD_CHANNEL_ID"])

POOL_FILE = "pool.json"

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ============================================================
# TELEGRAM API
# ============================================================

def telegram(method, **kwargs):
    response = requests.post(
        f"{API}/{method}",
        json=kwargs,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(
            f"Telegram API error: {data}"
        )

    return data["result"]


# ============================================================
# POOL
# ============================================================

def load_pool():

    if not os.path.exists(POOL_FILE):

        pool = {
            "last_update_id": 0,

            # The category posted last time.
            # Possible values:
            # testimony
            # motivation
            "last_type": None,

            # Last individual message ID
            "last_posted_id": None,

            # Last media group ID
            "last_posted_group_id": None,

            # All discovered source posts
            "messages": []
        }

        save_pool(pool)

        return pool

    with open(
        POOL_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        pool = json.load(f)

    # Backward compatibility
    if "last_update_id" not in pool:
        pool["last_update_id"] = 0

    if "last_type" not in pool:
        pool["last_type"] = None

    if "last_posted_id" not in pool:
        pool["last_posted_id"] = None

    if "last_posted_group_id" not in pool:
        pool["last_posted_group_id"] = None

    if "messages" not in pool:
        pool["messages"] = []

    return pool


def save_pool(pool):

    with open(
        POOL_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            pool,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# CLASSIFY POST
# ============================================================

def classify_message(message):

    """
    Motivation = video content.

    Everything else is treated as testimony.

    This means:
    - video
    - video_note
    - animation

    => motivation

    Everything else:
    => testimony
    """

    if message.get("video"):
        return "motivation"

    if message.get("video_note"):
        return "motivation"

    if message.get("animation"):
        return "motivation"

    return "testimony"


# ============================================================
# MEDIA GROUP
# ============================================================

def get_media_group_id(message):

    return message.get("media_group_id")


# ============================================================
# FETCH NEW SOURCE POSTS
# ============================================================

def fetch_new_messages(pool):

    print("=" * 60)
    print("TESTIMONY + MOTIVATION AUTO ROTATOR")
    print("=" * 60)

    print("SOURCE:", NEW_CHANNEL_ID)
    print("DESTINATION:", OLD_CHANNEL_ID)

    last_update_id = pool.get(
        "last_update_id",
        0
    )

    print(
        "Last update ID:",
        last_update_id
    )

    offset = last_update_id + 1

    updates = telegram(
        "getUpdates",
        offset=offset,
        limit=100,
        allowed_updates=["channel_post"]
    )

    print(
        "Updates received:",
        len(updates)
    )

    print(
        "Pool before:",
        len(pool["messages"])
    )

    newest_update_id = last_update_id

    existing_keys = {
        f"{item.get('chat_id')}:{item.get('id')}"
        for item in pool["messages"]
    }

    for update in updates:

        update_id = update.get("update_id")

        if update_id is None:
            continue

        newest_update_id = max(
            newest_update_id,
            update_id
        )

        post = update.get("channel_post")

        if not post:
            continue

        chat = post.get("chat", {})

        chat_id = str(
            chat.get("id")
        )

        message_id = post.get(
            "message_id"
        )

        if chat_id != NEW_CHANNEL_ID:

            print(
                "Skipped different channel:",
                chat_id
            )

            continue

        if message_id is None:
            continue

        unique_key = (
            f"{chat_id}:{message_id}"
        )

        if unique_key in existing_keys:

            print(
                "Already in pool:",
                message_id
            )

            continue

        # Determine category
        post_type = classify_message(post)

        media_group_id = get_media_group_id(post)

        text = (
            post.get("text")
            or post.get("caption")
            or ""
        )

        new_message = {
            "chat_id": chat_id,
            "id": message_id,
            "type": post_type,
            "media_group_id": media_group_id,
            "text": text
        }

        pool["messages"].append(
            new_message
        )

        existing_keys.add(unique_key)

        print("-" * 60)
        print("NEW POST FOUND")
        print("Message ID:", message_id)
        print("Type:", post_type)
        print(
            "Media group:",
            media_group_id or "None"
        )
        print(
            "Text:",
            text[:120]
        )

    pool["last_update_id"] = (
        newest_update_id
    )

    print("-" * 60)
    print(
        "Updated last update ID:",
        pool["last_update_id"]
    )

    print(
        "Pool after:",
        len(pool["messages"])
    )

    print("=" * 60)

    return pool


# ============================================================
# FIND ALBUM
# ============================================================

def get_album(pool, group_id):

    album = [
        message
        for message in pool["messages"]
        if (
            message.get("media_group_id")
            and
            str(message.get("media_group_id"))
            == str(group_id)
        )
    ]

    album.sort(
        key=lambda item: int(item["id"])
    )

    return album


# ============================================================
# COPY SINGLE MESSAGE
# ============================================================

def copy_single(message):

    message_id = message["id"]

    print("=" * 60)
    print("COPYING MESSAGE")
    print("Message:", message_id)
    print("Type:", message.get("type"))

    try:

        result = telegram(
            "copyMessage",
            chat_id=OLD_CHANNEL_ID,
            from_chat_id=NEW_CHANNEL_ID,
            message_id=message_id
        )

        print(
            "COPY SUCCESS:",
            result.get("message_id")
        )

        return True

    except Exception as error:

        print(
            "COPY FAILED:",
            error
        )

        return False


# ============================================================
# COPY ALBUM
# ============================================================

def copy_album(album):

    if not album:
        return False

    message_ids = [
        int(message["id"])
        for message in album
    ]

    message_ids.sort()

    print("=" * 60)
    print("COPYING ALBUM")
    print(
        "Messages:",
        message_ids
    )

    try:

        result = telegram(
            "copyMessages",
            chat_id=OLD_CHANNEL_ID,
            from_chat_id=NEW_CHANNEL_ID,
            message_ids=message_ids
        )

        print(
            "ALBUM COPY SUCCESS"
        )

        print(
            "Messages copied:",
            len(result)
        )

        return True

    except Exception as error:

        print(
            "ALBUM COPY FAILED:",
            error
        )

        return False


# ============================================================
# REMOVE STALE MESSAGE
# ============================================================

def remove_message_from_pool(
    pool,
    message
):

    message_id = str(
        message.get("id")
    )

    group_id = message.get(
        "media_group_id"
    )

    # If this is an album, remove
    # the whole album from the pool.
    if group_id:

        pool["messages"] = [
            item
            for item in pool["messages"]
            if str(
                item.get("media_group_id")
            )
            != str(group_id)
        ]

        print(
            "Removed stale album:",
            group_id
        )

    else:

        pool["messages"] = [
            item
            for item in pool["messages"]
            if str(item.get("id"))
            != message_id
        ]

        print(
            "Removed stale message:",
            message_id
        )


# ============================================================
# GET AVAILABLE CATEGORY
# ============================================================

def get_category_messages(
    pool,
    category
):

    return [
        message
        for message in pool["messages"]
        if message.get("type")
        == category
    ]


# ============================================================
# REMOVE IMMEDIATE REPEAT
# ============================================================

def remove_recent_repeat(
    messages,
    pool
):

    last_id = pool.get(
        "last_posted_id"
    )

    last_group_id = pool.get(
        "last_posted_group_id"
    )

    filtered = []

    for message in messages:

        message_id = str(
            message.get("id")
        )

        group_id = message.get(
            "media_group_id"
        )

        # Don't immediately reuse
        # the exact previous message.
        if (
            last_id is not None
            and
            message_id == str(last_id)
        ):
            continue

        # Don't immediately reuse
        # the previous album.
        if (
            group_id
            and
            last_group_id
            and
            str(group_id)
            == str(last_group_id)
        ):
            continue

        filtered.append(message)

    return filtered


# ============================================================
# CHOOSE RANDOM MESSAGE
# ============================================================

def choose_random_message(
    pool,
    category
):

    candidates = get_category_messages(
        pool,
        category
    )

    if not candidates:

        return None

    # Try to avoid immediate repeat.
    filtered = remove_recent_repeat(
        candidates,
        pool
    )

    if filtered:

        candidates = filtered

    return random.choice(
        candidates
    )


# ============================================================
# POST NEXT MESSAGE
# ============================================================

def post_next(pool):

    print("=" * 60)
    print("CHOOSING NEXT CATEGORY")
    print("=" * 60)

    last_type = pool.get(
        "last_type"
    )

    print(
        "Last posted type:",
        last_type
    )

    # --------------------------------------------------------
    # STRICT ROTATION
    # --------------------------------------------------------

    if last_type == "testimony":

        next_type = "motivation"

    elif last_type == "motivation":

        next_type = "testimony"

    else:

        # First ever post.
        # Start with testimony.
        next_type = "testimony"

    print(
        "Next type:",
        next_type
    )

    # --------------------------------------------------------
    # FIND POSTS OF THAT TYPE
    # --------------------------------------------------------

    choice = choose_random_message(
        pool,
        next_type
    )

    # --------------------------------------------------------
    # IF CATEGORY DOESN'T EXIST
    # --------------------------------------------------------

    if choice is None:

        print(
            "No posts available for:",
            next_type
        )

        # If one category doesn't exist yet,
        # use the other category temporarily.
        fallback_type = (
            "motivation"
            if next_type == "testimony"
            else "testimony"
        )

        fallback = choose_random_message(
            pool,
            fallback_type
        )

        if fallback is None:

            print(
                "No posts available at all."
            )

            return pool

        print(
            "Fallback type:",
            fallback_type
        )

        choice = fallback

        next_type = fallback_type

    # --------------------------------------------------------
    # CHECK ALBUM
    # --------------------------------------------------------

    group_id = choice.get(
        "media_group_id"
    )

    if group_id:

        album = get_album(
            pool,
            group_id
        )

        print(
            "ALBUM DETECTED"
        )

        print(
            "Group:",
            group_id
        )

        print(
            "Items:",
            len(album)
        )

        success = copy_album(
            album
        )

        if success:

            pool["last_type"] = (
                next_type
            )

            pool["last_posted_id"] = (
                album[-1]["id"]
            )

            pool["last_posted_group_id"] = (
                group_id
            )

            print(
                "Album marked as posted."
            )

        else:

            # The source message may have
            # been deleted or become unavailable.
            print(
                "Album could not be copied."
            )

            # Remove it so the bot doesn't
            # keep selecting a dead post.
            for item in album:

                if item in pool["messages"]:

                    pool["messages"].remove(
                        item
                    )

        return pool

    # --------------------------------------------------------
    # SINGLE MESSAGE
    # --------------------------------------------------------

    print(
        "SINGLE MESSAGE"
    )

    print(
        "Message ID:",
        choice["id"]
    )

    print(
        "Type:",
        next_type
    )

    success = copy_single(
        choice
    )

    if success:

        pool["last_type"] = (
            next_type
        )

        pool["last_posted_id"] = (
            choice["id"]
        )

        pool["last_posted_group_id"] = None

        print(
            "Message marked as posted."
        )

    else:

        print(
            "Message unavailable."
        )

        # Remove stale source message.
        remove_message_from_pool(
            pool,
            choice
        )

    return pool


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("🚀 TESTIMONY + MOTIVATION ROTATOR")
    print("")

    pool = load_pool()

    # 1. Get new posts from source
    pool = fetch_new_messages(
        pool
    )

    # 2. Choose the correct category
    # 3. Randomly choose a post
    # 4. Copy it to destination
    pool = post_next(
        pool
    )

    # 5. Save state
    save_pool(
        pool
    )

    print("")
    print("=" * 60)
    print("POOL SAVED")
    print(
        "Last type:",
        pool.get("last_type")
    )
    print(
        "Pool size:",
        len(pool["messages"])
    )
    print("=" * 60)
    print("DONE")
    print("")


if __name__ == "__main__":
    main()
