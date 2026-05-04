FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm config set fetch-retries 5 \
	&& npm config set fetch-retry-mintimeout 20000 \
	&& npm config set fetch-retry-maxtimeout 120000 \
	&& npm config set prefer-offline true
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
RUN apk add --no-cache bash
COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY --from=build /app/dist/ /usr/share/nginx/html/
EXPOSE 8099
CMD ["/bin/sh", "-c", "envsubst '${AZTDP_INTERNAL_TOKEN}' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf && nginx -g 'daemon off;'"]
