# Imagen del dashboard para Cloud Run (usuario sin privilegios, puerto 8080).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# En producción solo se lee la API real: el mock no se publica.
ENV VITE_DATA_SOURCE=api
RUN npm run build && rm -rf dist/mock

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
