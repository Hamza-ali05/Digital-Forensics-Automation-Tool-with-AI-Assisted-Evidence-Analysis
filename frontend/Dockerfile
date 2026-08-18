# DFAT frontend — production static build served by nginx
FROM node:18-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --legacy-peer-deps

COPY public ./public
COPY src ./src

ENV NODE_OPTIONS=--openssl-legacy-provider
ENV REACT_APP_API_BASE_URL=/api/v1
ENV CI=true

# package.json "build" uses Windows "set"; invoke react-scripts directly on Linux.
RUN npx react-scripts build

FROM nginx:alpine AS production

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/build /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
