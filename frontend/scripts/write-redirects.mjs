// Netlify build step: writes public/_redirects so /api/* is proxied to the backend.
import { writeFileSync } from "node:fs";

const origin = (process.env.API_ORIGIN ?? "").trim().replace(/\/+$/, "");
if (!/^https:\/\/[^/\s]+$/.test(origin)) {
  console.error("API_ORIGIN must be the backend URL, e.g. https://paprika-api.onrender.com");
  process.exit(1);
}

writeFileSync(
  new URL("../public/_redirects", import.meta.url),
  `/api/*  ${origin}/api/:splat  200!\n/*  /index.html  200\n`,
);
console.log(`_redirects: /api/* -> ${origin}`);
