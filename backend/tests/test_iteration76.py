"""Iteration 76 — Comment delete permission expansion.

Verifies the two ownership paths and the outsider rejection for the
DELETE /api/posts/{post_id}/comments/{comment_id} endpoint:

  1. Comment author can delete their own comment on someone else's post.
  2. Post author can delete someone else's comment on their own post.
  3. Outsider (neither) gets 404 (same shape as "not found" so we
     don't leak the existence of comments they can't touch).
  4. Cascade — deleting a comment also drops its comment_likes rows.
  5. `CommentOut.can_delete` is True for both viewer paths and False
     for the outsider.
"""
from __future__ import annotations
import asyncio
import os
import secrets
import uuid
from datetime import datetime, timezone

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _fresh_db():
    client = AsyncIOMotorClient(MONGO_URL)
    return client, client[DB_NAME]


async def _seed(tag: str):
    """Create a post + 1 comment + 1 comment-like. Returns handles."""
    client, db = await _fresh_db()
    post_author = f"u-post-{tag}"
    commenter = f"u-comment-{tag}"
    outsider = f"u-out-{tag}"
    post_id = f"p-{tag}"
    comment_id = f"c-{tag}"
    now = datetime.now(timezone.utc).isoformat()

    await db.posts.insert_one({
        "id": post_id,
        "author_uid": post_author,
        "body": "test post",
        "created_at": now,
        "visibility": "public",
        "kind": "post",
        "_test_tag": tag,
    })
    await db.post_comments.insert_one({
        "id": comment_id,
        "post_id": post_id,
        "author_uid": commenter,
        "body": "test comment",
        "created_at": now,
        "_test_tag": tag,
    })
    await db.post_comment_likes.insert_one({
        "comment_id": comment_id,
        "user_uid": outsider,
        "created_at": now,
        "_test_tag": tag,
    })
    client.close()
    return {
        "post_id": post_id,
        "comment_id": comment_id,
        "post_author": post_author,
        "commenter": commenter,
        "outsider": outsider,
    }


async def _cleanup(tag: str):
    client, db = await _fresh_db()
    for coll in ("posts", "post_comments", "post_comment_likes", "users"):
        await db[coll].delete_many({"_test_tag": tag})
    client.close()


def _call_delete_comment(post_id: str, comment_id: str, viewer_uid: str):
    """Call the endpoint handler directly with a mocked `current`."""
    from routers.posts_router import delete_comment
    return _run(delete_comment(
        post_id=post_id,
        comment_id=comment_id,
        current={"uid": viewer_uid, "email": f"{viewer_uid}@test"},
    ))


# ══════════════════════════════════════════════════════════════════
# 1) Comment author can delete their own comment
# ══════════════════════════════════════════════════════════════════
def test_comment_author_can_delete_their_own():
    tag = f"a-{uuid.uuid4().hex[:8]}"
    fx = _run(_seed(tag))
    try:
        res = _call_delete_comment(fx["post_id"], fx["comment_id"], fx["commenter"])
        assert res == {"ok": True}
        # Cascade — the like row is gone.
        async def _check():
            client, db = await _fresh_db()
            remaining = await db.post_comments.count_documents({"id": fx["comment_id"]})
            likes = await db.post_comment_likes.count_documents({"comment_id": fx["comment_id"]})
            client.close()
            return remaining, likes
        remaining, likes = _run(_check())
        assert remaining == 0
        assert likes == 0
    finally:
        _run(_cleanup(tag))


# ══════════════════════════════════════════════════════════════════
# 2) Post author can delete a comment on their post
# ══════════════════════════════════════════════════════════════════
def test_post_author_can_delete_others_comment():
    tag = f"b-{uuid.uuid4().hex[:8]}"
    fx = _run(_seed(tag))
    try:
        res = _call_delete_comment(fx["post_id"], fx["comment_id"], fx["post_author"])
        assert res == {"ok": True}
        async def _check():
            client, db = await _fresh_db()
            remaining = await db.post_comments.count_documents({"id": fx["comment_id"]})
            client.close()
            return remaining
        assert _run(_check()) == 0
    finally:
        _run(_cleanup(tag))


# ══════════════════════════════════════════════════════════════════
# 3) Outsider gets 404 (not 403 — deliberate leak-prevention)
# ══════════════════════════════════════════════════════════════════
def test_outsider_cannot_delete():
    from fastapi import HTTPException
    tag = f"c-{uuid.uuid4().hex[:8]}"
    fx = _run(_seed(tag))
    try:
        with pytest.raises(HTTPException) as exc:
            _call_delete_comment(fx["post_id"], fx["comment_id"], fx["outsider"])
        assert exc.value.status_code == 404
        # Comment survives.
        async def _check():
            client, db = await _fresh_db()
            remaining = await db.post_comments.count_documents({"id": fx["comment_id"]})
            client.close()
            return remaining
        assert _run(_check()) == 1
    finally:
        _run(_cleanup(tag))


# ══════════════════════════════════════════════════════════════════
# 4) Missing comment → 404 with distinct detail
# ══════════════════════════════════════════════════════════════════
def test_missing_comment_returns_404():
    from fastapi import HTTPException
    tag = f"d-{uuid.uuid4().hex[:8]}"
    fx = _run(_seed(tag))
    try:
        with pytest.raises(HTTPException) as exc:
            _call_delete_comment(fx["post_id"], "c-does-not-exist", fx["commenter"])
        assert exc.value.status_code == 404
        assert "Comment not found" in exc.value.detail
    finally:
        _run(_cleanup(tag))


# ══════════════════════════════════════════════════════════════════
# 5) can_delete is computed correctly for each viewer path
# ══════════════════════════════════════════════════════════════════
def test_can_delete_field_reflects_both_ownership_paths():
    from routers.posts_router import list_comments
    tag = f"e-{uuid.uuid4().hex[:8]}"
    fx = _run(_seed(tag))
    try:
        # Viewer = commenter → can_delete True (is_mine path)
        out = _run(list_comments(post_id=fx["post_id"],
                                    current={"uid": fx["commenter"], "email": "x@t"}))
        assert len(out) == 1
        assert out[0].is_mine is True
        assert out[0].can_delete is True

        # Viewer = post author → can_delete True (moderator path), is_mine False
        out = _run(list_comments(post_id=fx["post_id"],
                                    current={"uid": fx["post_author"], "email": "x@t"}))
        assert len(out) == 1
        assert out[0].is_mine is False
        assert out[0].can_delete is True

        # Viewer = outsider → both False
        out = _run(list_comments(post_id=fx["post_id"],
                                    current={"uid": fx["outsider"], "email": "x@t"}))
        assert len(out) == 1
        assert out[0].is_mine is False
        assert out[0].can_delete is False
    finally:
        _run(_cleanup(tag))
