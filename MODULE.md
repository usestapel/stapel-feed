# stapel-feed — MODULE.md

> Agent-facing map of this module: what it provides, where to extend it
> without forking, and what not to do. Kept in the same change as any edit
> to a seam. See also README.md and CHANGELOG.md.

## What this module provides

- **Posts** (`Post`): plain text ≤ 2000, ≤ `MAX_ATTACHMENTS` opaque CDN refs,
  `public | followers`, status `published | blocked | deleted`, denormalized
  `comment_count` and `reaction_counts`.
- **Comments** (`Comment`): flat, ≤ 1000. **Reactions** (`Reaction`): one per
  `(target, user)`, kinds from `REACTION_KINDS`.
- Four anchor-paginated reads (`home/`, `public/`, `authors/<id>/posts/`,
  `posts/<id>/` + `comments/`), writes, `PUT reactions/`, under `/feed/api/v1/`.
- Facts `feed.*`, Functions `feed.moderation_content`, `feed.counts`,
  `feed.export`, the moderation takedown consumer, GDPR owner `feed`.

## Extension points (fork-free)

### Settings — `STAPEL_FEED` namespace (`conf.py`, registry in CONFIG.MD)

| Key | Default | What it customizes |
|---|---|---|
| `PUBLIC_READ` | `True` | Axis. Anonymous reads of the public surfaces; `False` → 401. |
| `WRITE_REQUIRES_ACCOUNT` | `True` | Axis. Guest writes → `error.403.write_requires_account`. |
| `REACTION_KINDS` | `("like",)` | REPLACE. The reaction vocabulary. |
| `EDIT_WINDOW_MINUTES` | `15` | Author edits; `0` = none. |
| `FOLLOWING_MAX` | `5000` | Passed as `limit` to the graph; home serves the first N. |
| `MAX_ATTACHMENTS` | `10` | Per post (≤ 100). |
| `SOCIAL_GRAPH_FUNCTION` | `"profiles.social_graph"` | REPLACE. Dotted comm name. |
| `CARDS_FUNCTION` / `MEDIA_FUNCTION` | `"profiles.public_cards"` / `"cdn.describe_many"` | REPLACE; `""` disables (degraded rendering). |
| `NOTIFY` / `NOTIFY_FOLLOWERS` | `True` / `False` | Author notifications / reserved follower fan-out (W003). |
| `POST_URL_TEMPLATE` | `""` | `{post_id}` link for notifications and moderation. |

### The graph seam (`services/graph.py`)

One Function, `{user_id, limit}` → `{following: [ids], blocked: [ids],
truncated}`; `blocked` is undirected. `home/` and an authenticated
`public/` call it and answer **503** `social_graph_unavailable` when it
cannot be asked; `authors/<id>/posts/`, `posts/<id>/` and comments degrade
(`graph_or_unknown`): public content only, no block filter. Writes on a
pair (comment, react) need it too: blocked → 403 `blocked`, unreachable → 503.

### Moderation (`actions.py`, `functions.py`)

The composite registers two target types (the stapel-social preset, only
when moderation is selected): `post` with `id_field: "post_id"` and
`comment` with `id_field: "comment_id"`, both
`content_function: "feed.moderation_content"`. `moderation.completed`:
`rejected` → `blocked` (hidden from every read; the author sees `blocked`
on their own detail), `approved` on a blocked row → `published`.

### Serializer seams and presenters (`views.py`, `presenters.py`)

Views inherit `StapelAPIView`. Presentation swaps via
`STAPEL_SWAP["STAPEL_FEED_POST_PRESENTER"]` / `["STAPEL_FEED_COMMENT_PRESENTER"]`.
A page is presented with one cards call, one media call and one reactions query.

| View | Request | Response |
|---|---|---|
| `HomeFeedView`, `PublicFeedView`, `AuthorPostsView` (GET) | — | `PostPage` |
| `PostsView` (POST) | `PostCreateRequestSerializer` | `PostResponseSerializer` (201) |
| `PostDetailView` (GET, PATCH, DELETE) | `PostUpdateRequestSerializer` | `PostResponseSerializer` / 204 |
| `PostCommentsView` (GET, POST) | `CommentCreateRequestSerializer` | `CommentPage` / `CommentResponseSerializer` |
| `CommentDetailView` (DELETE) | — | 204 |
| `ReactionsView` (PUT) | `ReactionToggleRequestSerializer` | `ReactionStateResponseSerializer` |

Guest stance: `home/` is `IsNotAnonymousUser` + `ANONYMOUS_DENIED`; public
reads `AllowAny` + `ANONYMOUS_ALLOWED` (`PUBLIC_READ` in the body); writes
`IsAuthenticated` + `ANONYMOUS_ALLOWED` (`WRITE_REQUIRES_ACCOUNT` in the body).

### Events & functions (comm surface)

| Kind | Name | Payload | Schema |
|---|---|---|---|
| Action (emits) | `feed.post.created` | `{post_id, author_id, visibility}` | `schemas/emits/` |
| Action (emits) | `feed.post.deleted` | `{post_id, author_id}` | `schemas/emits/` |
| Action (emits) | `feed.comment.created` | `{comment_id, post_id, author_id, post_author_id}` | `schemas/emits/` |
| Action (emits) | `feed.reaction.changed` | `{target_type, target_key, user_id, kind, added, author_id}` | `schemas/emits/` |
| Action (consumes) | `user.merged` | `{from_user_id, into_user_id}` | `schemas/consumes/` |
| Action (consumes) | `moderation.completed` | `{target_type, target_key, decision}` | `schemas/consumes/` |
| Action (consumes) | `user.deleted`, `gdpr.erasure.requested` | via `register_gdpr_owner("feed", ["account"], …)` | core |
| Function (provides) | `feed.moderation_content` | `{post_id}` / `{comment_id}` → `{author_id, text, body, media, attachments, created_at, url}` | `schemas/functions/` |
| Function (provides) | `feed.counts` | `{user_id}` → `{posts}` | `schemas/functions/` |
| Function (provides) | `feed.export` | `{cursor, limit}` → `{rows, cursor, total}` | `schemas/functions/` |
| Function (calls) | `profiles.social_graph`, `profiles.public_cards`, `cdn.describe_many` | settings above | owners' schemas |
| Notification | `feed.comment_received`, `feed.reaction_received` (debounced 10 min per target) | variables `post_id`, `actor_id`, `post_url` | notifications registry |
| Signal | `feed:user:<post_author_id>` / `feed.activity` | `{post_id}` | no-op without a transport |

### Reserved, not built

`TIMELINE_MATERIALIZED`, `RANKING`, `HASHTAGS`, `MENTIONS`; reposts, groups,
stories; `NOTIFY_FOLLOWERS` fan-out (needs a followers Function in profiles).

## Contract emission

`make contract` emits `docs/{schema,flows,errors,capabilities}.json`,
`docs/llms.txt` and README.md (from `docs/readme.md`), on Python 3.12.
Enum names are pinned in `_codegen_settings.enum_name_overrides()`.

## Anti-patterns

- **Never import a sibling module** (`stapel_profiles`, `stapel_cdn`,
  `stapel_moderation`); `tests/test_architecture.py` greps the package.
- **Never serve home/public without the graph** — a missing block check is a 503.
- **Never `+= 1` a counter** on a value read earlier; recount under the row lock.
- **Never put a body on the bus**; events carry identity only.
