# --- build stage ---
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY tsconfig.json vite.config.ts tailwind.config.js postcss.config.js index.html ./
COPY src ./src
RUN npm run build

# --- runtime (nginx) ---
FROM nginx:1.27-alpine
# v0.9.4: tzdata (Europe/Istanbul) + TZ env
RUN apk add --no-cache tzdata && \
    cp /usr/share/zoneinfo/Europe/Istanbul /etc/localtime && \
    echo "Europe/Istanbul" > /etc/timezone
ENV TZ=Europe/Istanbul
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -q --spider http://localhost/ || exit 1
