// Copy to config.js (git-ignored) and fill in. NEVER commit the real secret.
export const EC2_API_URL = 'https://dl.example.com';   // your EC2 API (Caddy/nginx HTTPS)
export const API_SECRET = 'change-me-to-a-long-random-string'; // must match EC2 .env API_SECRET
