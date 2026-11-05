"""Business flows of stapel-feed (stapel_core.flows).

The Flow objects live here; HTTP steps are attached in ``views.py`` with
``@flow_step``. Literals are the canonical English source texts; i18n keys
are derived (``flow.<id>.title`` / ``.step.<order>.note``).
"""
from stapel_core.flows import Flow

POST = Flow(
    "feed.post",
    title="Post an update",
    description=(
        "A member writes a post (text, a few uploaded pictures, public or for "
        "followers). It appears at once on their own and their followers' home "
        "feeds; the author may edit it for a short window and delete it any time."
    ),
    actors=["Member (a guest when WRITE_REQUIRES_ACCOUNT is off)"],
)
POST.human(order=1, note="The member opens the composer on the feed")
POST.action("feed.post.created", order=6, note="The new post is announced (identity only, no body)")

PUBLIC_READ = Flow(
    "feed.public_read",
    title="Read the community",
    description=(
        "Anyone reads the public feed, an author's posts and one post with its "
        "comments. Followers-only posts reach followers only; blocked authors "
        "are hidden in both directions."
    ),
    actors=["Visitor (when PUBLIC_READ is on)", "Member"],
)

REACT_COMMENT = Flow(
    "feed.react_comment",
    title="React and comment",
    description=(
        "A member likes a post and writes a comment under it; the counts move in "
        "the same transaction, and the post's author is notified."
    ),
    actors=["Member"],
)
REACT_COMMENT.action("feed.reaction.changed", order=5, note="The reaction change is announced")
REACT_COMMENT.action("feed.comment.created", order=6, note="The comment is announced to the post author")
