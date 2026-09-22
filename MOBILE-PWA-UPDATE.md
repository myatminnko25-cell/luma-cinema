# Luma Cinema Mobile / PWA update

## GitHub / Render update
1. Unzip Luma-Cinema-Mobile-PWA-Update.zip.
2. Open your existing GitHub luma-cinema repository on the branch Render deploys.
3. Add file → Upload files. Drag the included `dist` folder and MOBILE-PWA-UPDATE.md into the repository root. Preserve the dist/ paths. Do not upload the ZIP itself or nest the files inside another folder.
4. Commit: Fix Bunny HLS playback and add mobile PWA.
5. Wait for Render deploy to complete, or use Manual Deploy → Deploy latest commit.
6. Reload the website and test the same Bunny playlist link.

This patch changes viewer files only. Existing server.py, Supabase tables, Render environment variables and admin episode-grouping implementation do not need replacement.

## Phone installation
- iPhone: open https://luma-cinema.onrender.com in Safari → Share → Add to Home Screen → Add. Enable Open as Web App if that option is shown.
- Android: Chrome → menu → Install app / Add to Home screen. The site's Home Screen button opens the install prompt when available, otherwise instructions.
- Internet is required for catalog and videos. This is not an offline video downloader.
- Favorites/progress remain local to each browser/installed app; installation may use separate storage on iOS.
- APK packaging is deferred as requested.

## Playback change and diagnosis
The previous player preferred native HLS whenever canPlayType returned a truthy value. In the test Chromium browser the original player failed with readyState 0. With the same supplied Bunny playlist, the updated player decoded 480x240 frames, advanced playback, and sought forward successfully.
Chromium/Android now prefer bundled HLS.js when supported. Safari with native HLS support retains native playback. Unsupported browsers show an explanatory error. Network/media recovery is bounded; 401/403/404 responses have specific guidance. Old callbacks cannot replace a newer video's error state.
Bunny also returned 403 for a localhost Referer, but accepted the Render origin and requests matching the production no-referrer policy. Keep the existing server Referrer-Policy. If using a new custom domain, configure Bunny's allowed domains appropriately; never put Bunny API/signing secrets in frontend code.

## Verification
- Actual supplied HLS video: original failure reproduced; updated playback, seek and saved progress checked in Chromium desktop browser at mobile viewport.
- Series grouping/admin append/duplicate guard regression test passed.
- Player selection/retry/access-error/stale-event/cleanup tests passed.
- PWA manifest/icons and offline/API/admin/stream routing tests passed.
- Mobile viewport and installation help checked.
- Physical iPhone installation, Safari decoding, physical Android and LG TV playback remain unverified. Production deployment is not performed by this ZIP.

Player reference: https://github.com/video-dev/hls.js
