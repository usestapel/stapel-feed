# CONFIG.MD — stapel-feed

Config registry for **stapel-feed**. One row per configuration key the
module reads, its **source** (`env` = the process environment / the
`STAPEL_FEED` settings dict), what it is for, whether it is required, and
its default.

Every key is read through `feed_settings` (`stapel_feed.conf`, namespace
`STAPEL_FEED`). Resolution order per key: `settings.STAPEL_FEED` dict → a
flat Django setting of the same name → environment variable → the default
below. `PUBLIC_READ` and `WRITE_REQUIRES_ACCOUNT` are CTO-facing config axes.

## stapel-feed

| Key | Source | Purpose | Required | Default |
|-----|--------|---------|----------|---------|
| PUBLIC_READ | env | axis: unauthenticated visitors read `public/`, `authors/<id>/posts/`, `posts/<id>/` and its comments; false → 401. | no | true |
| WRITE_REQUIRES_ACCOUNT | env | axis: a guest session is refused on every write with `error.403.write_requires_account`. | no | true |
| REACTION_KINDS | settings | the reaction vocabulary (replaces the default); unknown kinds answer 400. Malformed is system check E001. | no | ("like",) |
| EDIT_WINDOW_MINUTES | env | minutes after creation the author may edit; 0 = no edits; after → 409 `edit_window_closed`. | no | 15 |
| FOLLOWING_MAX | env | followed authors `home/` fans in at most; over it the graph answers `truncated` and home serves the newest N follows. | no | 5000 |
| MAX_ATTACHMENTS | env | attachments per post (≤ 100). | no | 10 |
| SOCIAL_GRAPH_FUNCTION | env | comm Function `{user_id, limit}` → `{following, blocked, truncated}`; unreachable is W001 and 503 on home/public. | no | profiles.social_graph |
| CARDS_FUNCTION | env | comm Function for author cards, batched per page; "" disables (cards null). | no | profiles.public_cards |
| MEDIA_FUNCTION | env | comm Function for attachment metadata; "" disables (image objects keep the ref). | no | cdn.describe_many |
| NOTIFY | env | best-effort `feed.comment_received` / `feed.reaction_received` to the post author. | no | true |
| NOTIFY_FOLLOWERS | env | reserved fan-out of `feed.new_post_from_followed`; true is W003 (nothing is sent yet). | no | false |
| POST_URL_TEMPLATE | env | `{post_id}` template for notification and moderation links; empty = none. | no | "" |
