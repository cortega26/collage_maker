# Security Notes

This release introduces basic input validation for file paths used by the desktop
application.  The validation mitigates simple path-manipulation attacks by
ensuring:

- Only existing files with approved image extensions are accepted for loading.
- Save destinations must reside in existing directories and use approved
  extensions.
- URL-like paths (e.g., `http://example.com`) are rejected to prevent accidental
  remote resource usage.

Residual risks include handling of potentially malicious image files, which
relies on the security of the underlying image libraries.  No network requests
or database queries are performed by the application.
