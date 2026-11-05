"""comm Functions provided by stapel-feed (schemas in ``schemas/functions/``).

- ``feed.moderation_content`` — what a moderator reads about a post or a
  comment (``{post_id}`` / ``{comment_id}``; a bare ``target_key`` names a
  post). Raises ``LookupError`` for an absent target, the contract of the
  ``*.moderation_content`` family.
- ``feed.counts`` — a user's published post count.
- ``feed.export`` — cursor snapshot of posts (identity and counters, no body).
"""
from stapel_core.comm import function

EXPORT_DEFAULT_LIMIT = 100
EXPORT_MAX_LIMIT = 500


@function("feed.moderation_content")
def moderation_content(payload):
    from .models import Comment, Post
    from .services.events import post_url

    def _key(name):
        value = payload.get(name)
        text = str(value) if value is not None else ""
        return int(text) if text.isdigit() else None

    comment_id = _key("comment_id")
    if comment_id is not None or payload.get("comment_id") is not None:
        comment = Comment.objects.filter(pk=comment_id).first() if comment_id is not None else None
        if comment is None:
            raise LookupError(f"comment {payload.get('comment_id')!r} not found")
        return {
            "author_id": str(comment.author_id),
            "text": comment.body,
            "body": comment.body,
            "media": [],
            "attachments": [],
            "created_at": comment.created_at.isoformat(),
            "url": post_url(comment.post_id),
        }
    post_id = _key("post_id")
    if post_id is None:
        post_id = _key("target_key")
    post = Post.objects.filter(pk=post_id).first() if post_id is not None else None
    if post is None:
        raise LookupError(f"post {payload.get('post_id', payload.get('target_key'))!r} not found")
    refs = list(post.attachments or [])
    return {
        "author_id": str(post.author_id),
        "text": post.body,
        "body": post.body,
        "media": refs,
        "attachments": refs,
        "created_at": post.created_at.isoformat(),
        "url": post_url(post.pk),
    }


@function("feed.counts")
def counts(payload):
    from .services.posts import published_count

    return {"posts": published_count(str(payload["user_id"]))}


@function("feed.export")
def export(payload):
    from .models import Post

    limit = min(int(payload.get("limit") or EXPORT_DEFAULT_LIMIT), EXPORT_MAX_LIMIT)
    cursor = payload.get("cursor")
    qs = Post.objects.order_by("id")
    if cursor and str(cursor).isdigit():
        qs = qs.filter(id__gt=int(cursor))
    page = list(qs[: limit + 1])
    more = len(page) > limit
    page = page[:limit]
    rows = [
        {
            "post_id": str(post.pk),
            "author_id": str(post.author_id),
            "visibility": post.visibility,
            "status": post.status,
            "comment_count": post.comment_count,
            "reaction_counts": dict(post.reaction_counts or {}),
            "created_at": post.created_at.isoformat(),
            "seq": post.pk,
        }
        for post in page
    ]
    return {
        "rows": rows,
        "cursor": str(page[-1].pk) if more and page else None,
        "total": Post.objects.count(),
    }
