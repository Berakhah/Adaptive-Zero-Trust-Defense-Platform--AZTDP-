FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm config set fetch-retries 5 \
	&& npm config set fetch-retry-mintimeout 20000 \
	&& npm config set fetch-retry-maxtimeout 120000 \
	&& npm config set prefer-offline true
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY . .
RUN npm run build

FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10
RUN apk add --no-cache bash
COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY entrypoint.sh /entrypoint.sh
COPY --from=build /app/dist/ /usr/share/nginx/html/
# Run as the image's unprivileged nginx user (uid 101): the entrypoint renders
# /etc/nginx/nginx.conf and htpasswd at start, and nginx needs its cache dirs.
RUN chmod +x /entrypoint.sh \
 && chown -R nginx:nginx /etc/nginx /var/cache/nginx
USER 101:101
EXPOSE 8099
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8099/healthz"]
CMD ["/entrypoint.sh"]
