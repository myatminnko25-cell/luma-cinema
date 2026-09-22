# Viewer / Admin

Viewer: https://luma-cinema.onrender.com/
Admin: https://luma-cinema.onrender.com/admin

Viewer no longer contains an Admin navigation link. Admin keeps its existing password/session authentication. These are separate pages on the same deployment, not separate servers or domains. Hiding the link is not the security boundary; existing server authentication protects changes.

Upload the included dist folder to the existing GitHub repository root, preserving dist paths, and commit. This cumulative patch includes the previous Mobile/PWA and HLS player update. No Supabase or Render environment changes are required.
