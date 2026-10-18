# Builds the React app (frontend/) and serves it with nginx on Cloud Run.
# Both API URLs are baked in at build time from .env.production (written by deploy.sh).
FROM mirror.gcr.io/library/node:22-slim AS build
WORKDIR /app
# W1 committed a complete package lock, so installs are reproducible and no source edits are needed.
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund
COPY . .
RUN CI=false npx craco build

FROM mirror.gcr.io/nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 8080
