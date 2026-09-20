FROM node:22.23.2-alpine3.24 AS build
WORKDIR /app
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.30.5-alpine3.24
COPY --from=build /app/dist /usr/share/nginx/html
HEALTHCHECK --interval=10s --timeout=3s --retries=10 CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
