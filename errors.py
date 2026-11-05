"""i18n error keys of stapel-feed.

Only ``error.<status>.<slug>`` keys leave this package — human-readable
strings are translations, never literals in responses.
"""
from stapel_core.django.api.errors import register_service_errors

ERR_400_ATTACHMENT_REF_INVALID = "error.400.attachment_ref_invalid"
ERR_400_TOO_MANY_ATTACHMENTS = "error.400.too_many_attachments"
ERR_400_REACTION_KIND_UNKNOWN = "error.400.reaction_kind_unknown"
ERR_403_WRITE_REQUIRES_ACCOUNT = "error.403.write_requires_account"
ERR_403_HOME_REQUIRES_ACCOUNT = "error.403.home_requires_account"
ERR_403_BLOCKED = "error.403.blocked"
ERR_403_NOT_AUTHOR = "error.403.not_author"
ERR_404_POST_NOT_FOUND = "error.404.post_not_found"
ERR_404_COMMENT_NOT_FOUND = "error.404.comment_not_found"
ERR_409_EDIT_WINDOW_CLOSED = "error.409.edit_window_closed"
ERR_503_SOCIAL_GRAPH_UNAVAILABLE = "error.503.social_graph_unavailable"

STAPEL_FEED_ERRORS = {
    ERR_400_ATTACHMENT_REF_INVALID: "This attachment is not a valid upload reference",
    ERR_400_TOO_MANY_ATTACHMENTS: "A post carries at most {max} attachments",
    ERR_400_REACTION_KIND_UNKNOWN: "Unknown reaction",
    ERR_403_WRITE_REQUIRES_ACCOUNT: "Sign in to post, comment or react",
    ERR_403_HOME_REQUIRES_ACCOUNT: "Sign in to see the people you follow",
    ERR_403_BLOCKED: "You cannot interact with this person",
    ERR_403_NOT_AUTHOR: "Only the author can do this",
    ERR_404_POST_NOT_FOUND: "Post not found",
    ERR_404_COMMENT_NOT_FOUND: "Comment not found",
    ERR_409_EDIT_WINDOW_CLOSED: "This post can no longer be edited",
    ERR_503_SOCIAL_GRAPH_UNAVAILABLE: "The feed is temporarily unavailable; try again shortly",
}

#: Explicit remediation where the status heuristic would mislead.
STAPEL_FEED_REMEDIATION = {
    ERR_403_WRITE_REQUIRES_ACCOUNT: "reauthenticate",
    ERR_403_HOME_REQUIRES_ACCOUNT: "reauthenticate",
    ERR_503_SOCIAL_GRAPH_UNAVAILABLE: "wait_and_retry",
}

register_service_errors(STAPEL_FEED_ERRORS, remediation=STAPEL_FEED_REMEDIATION)

__all__ = [
    "STAPEL_FEED_ERRORS",
    "ERR_400_ATTACHMENT_REF_INVALID",
    "ERR_400_TOO_MANY_ATTACHMENTS",
    "ERR_400_REACTION_KIND_UNKNOWN",
    "ERR_403_WRITE_REQUIRES_ACCOUNT",
    "ERR_403_HOME_REQUIRES_ACCOUNT",
    "ERR_403_BLOCKED",
    "ERR_403_NOT_AUTHOR",
    "ERR_404_POST_NOT_FOUND",
    "ERR_404_COMMENT_NOT_FOUND",
    "ERR_409_EDIT_WINDOW_CLOSED",
    "ERR_503_SOCIAL_GRAPH_UNAVAILABLE",
]
