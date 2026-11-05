"""Row factories for the feed tests."""
from stapel_feed.models import Comment, Post, Reaction


def make_post(author, body="hello", **extra):
    return Post.objects.create(author_id=str(getattr(author, "pk", author)), body=body, **extra)


def make_comment(post, author, body="nice", **extra):
    return Comment.objects.create(post=post, author_id=str(getattr(author, "pk", author)), body=body, **extra)


def make_reaction(target_type, target_key, user, kind="like"):
    return Reaction.objects.create(
        target_type=target_type, target_key=str(target_key),
        user_id=str(getattr(user, "pk", user)), kind=kind,
    )
