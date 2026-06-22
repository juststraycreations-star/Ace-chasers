"""All Pydantic request/response models for the Ace Chasers API.

Kept in one module so routers don't pull in each other's models and so the
shapes the frontend sees stay easy to skim in a single place.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# --- Auth + Profile ---------------------------------------------------------

class ProfileIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    age: Optional[int] = Field(default=None, ge=13, le=120)
    skillLevel: Optional[str] = Field(default=None, max_length=20)
    location: Optional[str] = Field(default=None, max_length=120)
    favoriteCourse: Optional[str] = Field(default=None, max_length=120)
    favoriteFrisbee: Optional[str] = Field(default=None, max_length=120)
    homeCourse: Optional[str] = Field(default=None, max_length=120)
    interestedIn: Optional[str] = Field(default=None, max_length=200)
    bio: Optional[str] = Field(default=None, max_length=1000)
    interests: Optional[List[str]] = Field(default=None, max_length=20)
    profilePictureUrl: Optional[str] = Field(default=None, max_length=500)
    bannerUrl: Optional[str] = Field(default=None, max_length=500)
    # "Ace Club" membership: does the player belong to one? Optional ace count.
    aceClub: Optional[bool] = None
    aceClubCount: Optional[int] = Field(default=None, ge=0, le=10_000)
    privacy: Optional[dict] = None


class AuthSyncIn(BaseModel):
    invite_code: Optional[str] = None


class InviteCreateIn(BaseModel):
    email: Optional[str] = None
    expires_at: Optional[str] = None


class ProfileOut(BaseModel):
    uid: str
    email: Optional[str] = None
    emailVerified: bool = False
    name: Optional[str] = None
    age: Optional[int] = None
    skillLevel: Optional[str] = None
    location: Optional[str] = None
    favoriteCourse: Optional[str] = None
    favoriteFrisbee: Optional[str] = None
    bio: Optional[str] = None
    interests: List[str] = Field(default_factory=list)
    profilePictureUrl: Optional[str] = None
    bannerUrl: Optional[str] = None
    homeCourse: Optional[str] = None
    interestedIn: Optional[str] = None
    aceClub: Optional[bool] = None
    aceClubCount: Optional[int] = None
    privacy: dict = Field(default_factory=dict)


# --- Discovery / Swipes / Likes / Matches ----------------------------------

class SwipeIn(BaseModel):
    target_uid: str
    action: Literal["like", "pass"]


class LikeOut(BaseModel):
    player: ProfileOut
    likedAt: str
    matched: bool
    friended: bool


class RecentPost(BaseModel):
    id: str
    body: str
    created_at: str
    has_image: bool = False


class DiscoveryProfile(ProfileOut):
    """ProfileOut + the player's most recent public post (if any)."""
    recent_post: Optional[RecentPost] = None
    distance_miles: Optional[float] = None


class DiscoveryPage(BaseModel):
    players: List[DiscoveryProfile]
    next_cursor: Optional[str] = None


class FriendRequestOut(BaseModel):
    from_user: ProfileOut
    created_at: str


class IncomingLikeOut(BaseModel):
    from_user: ProfileOut
    liked_at: str


class InboxOut(BaseModel):
    incoming_likes: List[IncomingLikeOut] = Field(default_factory=list)
    incoming_friend_requests: List[FriendRequestOut] = Field(default_factory=list)
    sent_friend_request_uids: List[str] = Field(default_factory=list)
    friend_uids: List[str] = Field(default_factory=list)


# --- Posts -----------------------------------------------------------------

class PostAuthor(BaseModel):
    uid: str
    name: Optional[str] = None
    profilePictureUrl: Optional[str] = None


class PostOut(BaseModel):
    id: str
    body: str
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    visibility: Literal["public", "friends_only"]
    kind: Literal["post", "disc_review"] = "post"
    created_at: str
    author: PostAuthor
    is_mine: bool = False
    nice_count: int = 0
    down_count: int = 0
    liked_by_me: bool = False
    disliked_by_me: bool = False
    comment_count: int = 0
    recent_comments: List["CommentOut"] = Field(default_factory=list)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=500)


class CommentOut(BaseModel):
    id: str
    post_id: str
    body: str
    created_at: str
    author: PostAuthor
    is_mine: bool = False
    nice_count: int = 0
    liked_by_me: bool = False


# Resolve the forward reference now that CommentOut is defined.
PostOut.model_rebuild()


# --- Courses ----------------------------------------------------------------

class CourseIn(BaseModel):
    """Admin-facing payload for adding/editing a course."""
    name: str = Field(min_length=1, max_length=200)
    location: Optional[str] = Field(default=None, max_length=200)  # "City, State"
    description: Optional[str] = Field(default=None, max_length=2000)
    holes: Optional[int] = Field(default=None, ge=1, le=99)
    # "Ace Club" — does the course run an ace pot / club? When True, the
    # numeric value below holds the buy-in / member count (interpretation up
    # to the user; we just persist the integer).
    aceClub: bool = False
    aceClubCount: Optional[int] = Field(default=None, ge=0, le=10_000)


class CourseOut(CourseIn):
    id: str
    created_at: str
    review_count: int = 0
    avg_rating: Optional[float] = None  # 1-5


class CourseReviewIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)
    rating: int = Field(ge=1, le=5)


class CourseReviewOut(BaseModel):
    id: str
    course_id: str
    body: str
    rating: int
    created_at: str
    author: PostAuthor
    is_mine: bool = False
    # Course context is included on the global "recent reviews" feed so the
    # caller doesn't have to look it up separately.
    course_name: Optional[str] = None
    course_location: Optional[str] = None

