## What this is

Posts, comments, reactions and feeds for a Stapel community. Members post
plain-text updates with a few pictures; others comment and react; everyone
reads a home feed of the people they follow, a public feed, one author's
posts and one post with its comments. Following and blocks stay in
stapel-profiles and are read through one comm Function — the feed never
imports a sibling module.

## Quick start

```python
INSTALLED_APPS = [
    # ...
    "stapel_profiles",   # profiles.social_graph (>=0.23), profiles.public_cards
    "stapel_feed",
]

# urls.py
path("feed/api/", include("stapel_feed.urls"))   # -> /feed/api/v1/...

# Optional
STAPEL_FEED = {
    "PUBLIC_READ": True,            # anonymous visitors read public surfaces
    "WRITE_REQUIRES_ACCOUNT": True, # guests may not post, comment or react
    "REACTION_KINDS": ("like", "heart"),
}
```

## Concepts

- **Post** — `body` ≤ 2000 plain characters, ≤ 10 opaque CDN refs
  (`<kind>/<hash>`), `public` or `followers`. The author edits it within
  `EDIT_WINDOW_MINUTES` (15) and deletes it any time (soft).
- **Comment** — flat, ≤ 1000 characters; deleted by its author or the post's
  author. The post author is notified (`feed.comment_received`).
- **Reaction** — one per user per target, toggled with `PUT reactions/`
  (or set with `active`); counts move in the same transaction, recomputed
  from the rows under a row lock, so two writers cannot lose an update.
- **Reads** — `home/` (followed authors + own), `public/`,
  `authors/<id>/posts/`, `posts/<id>/` and its `comments/`; all
  anchor-paginated. Followers-only posts reach followers only; blocked
  authors are hidden in both directions; hidden answers like absent (404).
- **The 503 rule** — when `profiles.social_graph` cannot be asked, `home/`
  and members' `public/` answer `error.503.social_graph_unavailable` rather
  than show a blocked author. One author's page and one post degrade to
  public-only content.
- **Moderation** — `post` and `comment` target types read
  `feed.moderation_content`; a rejecting verdict hides the target (the
  author sees `blocked`).
- **GDPR** — erasure hard-deletes the person's posts, comments and
  reactions and recomputes the counters they touched.
