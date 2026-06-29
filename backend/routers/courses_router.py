"""Courses + course reviews routes.

GET    /api/courses                       — list (search + sort)
GET    /api/courses/recent-reviews        — most recent reviews across all
GET    /api/courses/{course_id}           — single course + aggregated stats
GET    /api/courses/{course_id}/reviews   — last N reviews for one course
POST   /api/courses/{course_id}/reviews   — add (one per user; upsert)
DELETE /api/courses/{course_id}/reviews/{review_id}  — author-only delete
POST   /api/admin/courses                 — admin-only add a course
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from db import get_db
from deps import require_admin
from firebase_auth import get_current_user
from models import (
    CourseIn,
    CourseOut,
    CourseReviewIn,
    CourseReviewOut,
    PostAuthor,
)

router = APIRouter()


def _course_doc_to_out(doc: dict) -> CourseOut:
    return CourseOut(
        id=doc["id"],
        name=doc["name"],
        location=doc.get("location"),
        description=doc.get("description"),
        holes=doc.get("holes"),
        aceClub=bool(doc.get("aceClub", False)),
        aceClubCount=doc.get("aceClubCount"),
        created_at=doc.get("created_at", ""),
        review_count=int(doc.get("_review_count") or 0),
        avg_rating=doc.get("_avg_rating"),
        submitted_by_name=doc.get("_submitter_name"),
    )


async def _attach_submitter_names(courses: list[dict]) -> None:
    """Mutate each course dict with `_submitter_name` (display name of
    the user who submitted it via POST /api/courses). One batched query
    regardless of list size. Courses without `submitted_by` (admin
    seeds) are left untouched."""
    submitter_uids = list({c["submitted_by"] for c in courses if c.get("submitted_by")})
    if not submitter_uids:
        return
    db = get_db()
    names: dict[str, str] = {}
    async for u in db.users.find(
        {"uid": {"$in": submitter_uids}},
        {"uid": 1, "name": 1, "_id": 0},
    ):
        n = (u.get("name") or "").strip()
        if n:
            names[u["uid"]] = n
    for c in courses:
        uid = c.get("submitted_by")
        if uid and uid in names:
            c["_submitter_name"] = names[uid]


async def _attach_course_stats(courses: list[dict]) -> None:
    """Mutate each course dict in place with `_review_count` + `_avg_rating`.

    One aggregation across all course ids — keeps the list page O(1) queries.
    """
    if not courses:
        return
    db = get_db()
    ids = [c["id"] for c in courses]
    pipeline = [
        {"$match": {"course_id": {"$in": ids}}},
        {
            "$group": {
                "_id": "$course_id",
                "n": {"$sum": 1},
                "avg": {"$avg": "$rating"},
            }
        },
    ]
    stats: dict[str, dict] = {}
    async for row in db.course_reviews.aggregate(pipeline):
        stats[row["_id"]] = row
    for c in courses:
        s = stats.get(c["id"])
        c["_review_count"] = (s or {}).get("n", 0)
        c["_avg_rating"] = round((s or {}).get("avg") or 0, 1) if s else None


@router.get("/api/courses", response_model=list[CourseOut])
async def list_courses(search: Optional[str] = None):
    """Public list of every course. Optional case-insensitive substring
    search across name + location."""
    db = get_db()
    query: dict = {}
    if search:
        pat = re.escape(search.strip())
        query["$or"] = [
            {"name": {"$regex": pat, "$options": "i"}},
            {"location": {"$regex": pat, "$options": "i"}},
        ]
    docs = await db.courses.find(query).sort("name", 1).to_list(length=500)
    await _attach_course_stats(docs)
    await _attach_submitter_names(docs)
    return [_course_doc_to_out(d) for d in docs]


@router.get("/api/courses/recent-reviews", response_model=list[CourseReviewOut])
async def recent_reviews(limit: int = 10, current=Depends(get_current_user)):
    """Most recent course reviews across the whole platform. Used by the
    /courses page sidebar."""
    limit = max(1, min(limit, 50))
    db = get_db()
    reviews = await (
        db.course_reviews.find({})
        .sort("created_at", -1)
        .limit(limit)
        .to_list(length=limit)
    )
    if not reviews:
        return []
    # Batch-fetch authors + course names in one shot each.
    author_uids = list({r["author_uid"] for r in reviews})
    course_ids = list({r["course_id"] for r in reviews})
    authors_by_uid: dict[str, dict] = {}
    courses_by_id: dict[str, dict] = {}
    async for u in db.users.find({"uid": {"$in": author_uids}}):
        authors_by_uid[u["uid"]] = u
    async for c in db.courses.find({"id": {"$in": course_ids}}):
        courses_by_id[c["id"]] = c

    out: list[CourseReviewOut] = []
    for r in reviews:
        a = authors_by_uid.get(r["author_uid"]) or {}
        c = courses_by_id.get(r["course_id"]) or {}
        out.append(
            CourseReviewOut(
                id=r["id"],
                course_id=r["course_id"],
                body=r["body"],
                rating=int(r["rating"]),
                created_at=r["created_at"],
                author=PostAuthor(
                    uid=r["author_uid"],
                    name=a.get("name"),
                    profilePictureUrl=a.get("profilePictureUrl"),
                ),
                is_mine=r["author_uid"] == current["uid"],
                course_name=c.get("name"),
                course_location=c.get("location"),
            )
        )
    return out


@router.get("/api/courses/{course_id}", response_model=CourseOut)
async def get_course(course_id: str):
    db = get_db()
    doc = await db.courses.find_one({"id": course_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Course not found")
    await _attach_course_stats([doc])
    await _attach_submitter_names([doc])
    return _course_doc_to_out(doc)


@router.get("/api/courses/{course_id}/reviews", response_model=list[CourseReviewOut])
async def list_course_reviews(
    course_id: str, limit: int = 10, current=Depends(get_current_user)
):
    """Most recent reviews for a single course (default last 10)."""
    limit = max(1, min(limit, 50))
    db = get_db()
    course = await db.courses.find_one({"id": course_id})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    reviews = await (
        db.course_reviews.find({"course_id": course_id})
        .sort("created_at", -1)
        .limit(limit)
        .to_list(length=limit)
    )
    author_uids = list({r["author_uid"] for r in reviews})
    authors_by_uid: dict[str, dict] = {}
    if author_uids:
        async for u in db.users.find({"uid": {"$in": author_uids}}):
            authors_by_uid[u["uid"]] = u
    return [
        CourseReviewOut(
            id=r["id"],
            course_id=r["course_id"],
            body=r["body"],
            rating=int(r["rating"]),
            created_at=r["created_at"],
            author=PostAuthor(
                uid=r["author_uid"],
                name=(authors_by_uid.get(r["author_uid"]) or {}).get("name"),
                profilePictureUrl=(authors_by_uid.get(r["author_uid"]) or {}).get("profilePictureUrl"),
            ),
            is_mine=r["author_uid"] == current["uid"],
            course_name=course.get("name"),
            course_location=course.get("location"),
        )
        for r in reviews
    ]


@router.post("/api/courses/{course_id}/reviews", response_model=CourseReviewOut)
async def add_course_review(
    course_id: str,
    payload: CourseReviewIn,
    current=Depends(get_current_user),
):
    """Upsert one review per user per course. Reposting overwrites the prior
    body + rating + updates the timestamp."""
    db = get_db()
    course = await db.courses.find_one({"id": course_id})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.course_reviews.find_one(
        {"course_id": course_id, "author_uid": current["uid"]}
    )
    if existing:
        await db.course_reviews.update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "body": payload.body,
                    "rating": payload.rating,
                    "created_at": now,
                }
            },
        )
        review_id = existing["id"]
    else:
        review_id = secrets.token_urlsafe(8)
        await db.course_reviews.insert_one(
            {
                "id": review_id,
                "course_id": course_id,
                "author_uid": current["uid"],
                "body": payload.body,
                "rating": payload.rating,
                "created_at": now,
            }
        )
    me = await db.users.find_one({"uid": current["uid"]}) or {}
    return CourseReviewOut(
        id=review_id,
        course_id=course_id,
        body=payload.body,
        rating=payload.rating,
        created_at=now,
        author=PostAuthor(
            uid=current["uid"],
            name=me.get("name"),
            profilePictureUrl=me.get("profilePictureUrl"),
        ),
        is_mine=True,
        course_name=course.get("name"),
        course_location=course.get("location"),
    )


@router.delete("/api/courses/{course_id}/reviews/{review_id}")
async def delete_course_review(
    course_id: str, review_id: str, current=Depends(get_current_user)
):
    db = get_db()
    res = await db.course_reviews.delete_one(
        {"id": review_id, "course_id": course_id, "author_uid": current["uid"]}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Review not found or not yours")
    return {"ok": True}


@router.post("/api/courses", response_model=CourseOut)
async def add_course(
    payload: CourseIn,
    current=Depends(get_current_user),
):
    """Any signed-in user can add a course to the community list.

    To avoid trivial duplicates we reject when an existing course already
    matches the same name + location (case-insensitive). The submitter's
    uid is stored as `submitted_by` for moderation.
    """
    db = get_db()
    name = payload.name.strip()
    location = (payload.location or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Course name is required")

    dup_query: dict = {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    if location:
        dup_query["location"] = {
            "$regex": f"^{re.escape(location)}$",
            "$options": "i",
        }
    existing = await db.courses.find_one(dup_query)
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A course with that name and location already exists.",
        )

    course_id = secrets.token_urlsafe(8)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": course_id,
        "name": name,
        "location": location or None,
        "description": (payload.description or None),
        "holes": payload.holes,
        "aceClub": payload.aceClub,
        "aceClubCount": payload.aceClubCount,
        "created_at": now,
        "submitted_by": current["uid"],
    }
    await db.courses.insert_one(doc)
    doc["_review_count"] = 0
    doc["_avg_rating"] = None
    # Surface the submitter name on the immediate response so the
    # frontend can show the "Suggested by …" credit without a refetch.
    submitter_name = (current.get("name") or "").strip()
    if submitter_name:
        doc["_submitter_name"] = submitter_name
    return _course_doc_to_out(doc)


# --- Admin ------------------------------------------------------------------

@router.post("/api/admin/courses", response_model=CourseOut, dependencies=[Depends(require_admin)])
async def admin_add_course(payload: CourseIn):
    """Admin-only: insert a new course."""
    db = get_db()
    course_id = secrets.token_urlsafe(8)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": course_id,
        "name": payload.name,
        "location": payload.location,
        "description": payload.description,
        "holes": payload.holes,
        "aceClub": payload.aceClub,
        "aceClubCount": payload.aceClubCount,
        "created_at": now,
    }
    await db.courses.insert_one(doc)
    doc["_review_count"] = 0
    doc["_avg_rating"] = None
    return _course_doc_to_out(doc)


@router.delete("/api/admin/courses/{course_id}", dependencies=[Depends(require_admin)])
async def admin_delete_course(course_id: str):
    db = get_db()
    await db.course_reviews.delete_many({"course_id": course_id})
    res = await db.courses.delete_one({"id": course_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Course not found")
    return {"ok": True}
