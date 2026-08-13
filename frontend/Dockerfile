FROM node:22-alpine AS build

WORKDIR /app
RUN corepack enable

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend ./
ARG VITE_API_BASE_URL=/api
ARG VITE_ASR_WS_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_ASR_WS_URL=${VITE_ASR_WS_URL}
RUN pnpm build

FROM nginx:1.27-alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
