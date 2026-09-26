# Frontend: Vite build → nginx (proxies /api to backend).
# Build from repo root: docker build -f frontend/Dockerfile --build-arg VITE_API_KEY=... .

FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

ARG VITE_API_KEY=change-me-local-api-key
ENV VITE_API_KEY=$VITE_API_KEY

RUN npm run build

FROM nginx:alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
