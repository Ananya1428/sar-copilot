# Multi-stage build (blueprint §21): Vite build -> nginx-served static.
FROM node:20-slim AS build
WORKDIR /srv

# Dependencies installed from package*.json first so this layer caches
# independently of source changes (same reasoning as api/Dockerfile).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Baked in at build time — Vite env vars are compiled into the bundle,
# not read at container start. Defaults to the nginx-proxied relative
# path (blueprint §21's `nginx` service fronts both `web` and `api` on
# one origin), overridable via `docker compose build --build-arg`.
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM nginx:alpine AS runtime
COPY --from=build /srv/dist /usr/share/nginx/html
# SPA fallback: any path nginx doesn't have a file for goes to index.html
# so client-side routing (react-router) handles it — the outer nginx
# reverse proxy (blueprint §21's `nginx` service) still owns /api/*.
RUN printf 'server {\n\
    listen 80;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80
