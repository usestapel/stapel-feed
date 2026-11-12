# Changelog

All notable changes to stapel-feed are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Pre-1.0 semver: **minor = breaking**, patch = compatible.

## [Unreleased]

## [0.1.0]

First release: posts, comments, reactions and feeds.

### Added
- **Posts**: plain text ≤ 2000, ≤ `MAX_ATTACHMENTS` (10) opaque CDN refs,
  `public | followers`; author edit inside `EDIT_WINDOW_MINUTES` (15, then
  `409 edit_window_closed`), soft delete any time.
- **Reads**, anchor-paginated `-id`: `home/` (followed + own), `public/`,
  `authors/<id>/posts/`, `posts/<id>/`. Hidden ≡ absent (404).
- **Graph client** over `profiles.social_graph` (`SOCIAL_GRAPH_FUNCTION`):
  unreachable → `error.503.social_graph_unavailable` on `home/` and members'
  `public/`; author pages and single posts degrade to public content.
  Blocked authors are hidden in both directions; writes on a blocked pair
  answer `403 blocked`.
- **Author cards** from `profiles.public_cards` and attachment image
  objects from `cdn.describe_many`, one call per page each, degrading to
  `null` / ref-only.
- **Typed image objects**: `ImageObject.variants` items are core's
  `VariantMeta` component (`tier` as a string, `branch`, `url`, `width`,
  `height` — the rungs profiles' `StapelImage` carries), and a top-level
  `url` names the default rendition (the `original` rung, else the largest;
  `null` when nothing was described). Author avatars get the same shape.
- **Comments** (flat) and **reactions** (one per user per target, toggle or
  set with `active`); counters recomputed from rows under the parent's row
  lock in the writer's transaction, unique constraint backstop.
- **Moderation**: `feed.moderation_content`, `moderation.completed`
  takedown (`rejected` → blocked, `approved` → published).
- **Events** `feed.post.created`, `feed.post.deleted`,
  `feed.comment.created`, `feed.reaction.changed` (identity only, in
  `mutate_and_emit`); notifications `feed.comment_received`,
  `feed.reaction_received` (debounced per target, 10 min, through
  `request_notification(dedup_key, dedup_ttl)`: the notifications intake
  delivers the first request per target in the window, the feed keeps no
  debounce state; needs `stapel-core>=0.95.3`); realtime
  `feed:user:<id>` / `feed.activity`.
- **Functions** `feed.counts`, `feed.export`. **`user.merged`** re-parents
  everything, keeping the oldest duplicate reaction.
- **Error catalogs** `translations/errors.{ru,es}.json` for every code in
  `errors.py` (with the `.state.json` provenance sidecar), shipped in the
  wheel, and the per-language error reference `docs/errors.{en,ru,es}.md`;
  `tests/test_error_i18n.py` gates coverage, drift, placeholders and
  foreign keys.
- **GDPR owner** `feed` (`account`): hard delete, counters recomputed.
- **Checks** E001 (reaction kinds), E002 (bounds), W001 (graph
  unreachable), W003 (`NOTIFY_FOLLOWERS` reserved). Admin with
  block/unblock actions through the services.
