"""Admin for stapel-feed.

Status moves only through the services (block/unblock actions), never a raw
field edit, so the parent's counters follow. Reactions are read-only.
"""
from django.contrib import admin

from .models import Comment, ContentStatus, Post, Reaction


def _status_action(service_name: str, status: str, label: str):
    def action(modeladmin, request, queryset):
        from .services import comments, posts

        service = posts if service_name == "posts" else comments
        for row in queryset:
            service.set_status(row.pk, status)
        modeladmin.message_user(request, f"{queryset.count()} row(s): {label}.")

    action.__name__ = f"{service_name}_{label}"
    action.short_description = f"{label.capitalize()} selected"
    return action


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "author_id", "visibility", "status", "comment_count", "created_at")
    list_filter = ("status", "visibility")
    search_fields = ("author_id", "body")
    readonly_fields = (
        "author_id", "body", "attachments", "visibility", "status", "comment_count",
        "reaction_counts", "created_at", "edited_at", "updated_at",
    )
    actions = [
        _status_action("posts", ContentStatus.BLOCKED, "block"),
        _status_action("posts", ContentStatus.PUBLISHED, "unblock"),
    ]

    def has_add_permission(self, request):
        return False


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "author_id", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("author_id", "body")
    readonly_fields = ("post", "author_id", "body", "status", "reaction_counts", "created_at", "updated_at")
    actions = [
        _status_action("comments", ContentStatus.BLOCKED, "block"),
        _status_action("comments", ContentStatus.PUBLISHED, "unblock"),
    ]

    def has_add_permission(self, request):
        return False


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = ("target_type", "target_key", "user_id", "kind", "created_at")
    list_filter = ("target_type", "kind")
    readonly_fields = ("target_type", "target_key", "user_id", "kind", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
