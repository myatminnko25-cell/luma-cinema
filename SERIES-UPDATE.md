# Series / Episode update

This patch uses the latest user-supplied ZIP as its base.

## Admin
- Series entries are grouped under one series heading.
- Use “＋ Episode ထည့်မယ်” on an existing series, or select it from the existing-series picker.
- The latest season and next episode number are prefilled. Changing season recalculates the next available number.
- Add the episode title and its video URL, then save. The new episode inherits the series thumbnail and synopsis as editable defaults.
- Existing episode edit/delete remains available. The add form blocks an already-listed season/episode number; this is a UI check, not a database uniqueness constraint.

## Viewer
- Home, Series, Favorites and Continue watching show one card per series.
- Opening that card shows all episodes sorted numerically by season and episode.
- Next episode, per-episode progress, existing playback hosts, thumbnails and synopsis remain supported.
- Series names are grouped ignoring case and repeated/outer spaces. Existing unrelated series with different names remain separate.

## Deployment
Replace the source files with this archive and redeploy the existing Render service using the same Supabase environment variables. No table changes, SQL migration or new credentials are needed. If a separate Netlify viewer is used, update its dist files too; its existing catalog publishing mechanism is unchanged.

Modified: dist/admin.html, dist/admin.js, dist/admin.css, dist/index.html, dist/app.js.
Added: dist/series.js, tests/test_series.js, SERIES-UPDATE.md.
server.py, Supabase integration, hosting configuration and existing catalog data are unchanged.

## Verification
`node tests/test_series.js` passes isolated DOM-based functional checks for grouping, episode sorting, next numbering, viewer filtering/details, admin append and duplicate protection. JavaScript syntax checks pass. No live Supabase writes or production deployment were performed, and physical LG TV testing was not performed.
