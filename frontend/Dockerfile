# ---------- build stage ----------
FROM node:20-slim AS builder

WORKDIR /app

# Copy dependency definitions
COPY package.json ./

# Install dependencies, bypassing peer dependency conflicts
RUN npm install --legacy-peer-deps

# Copy application source code
COPY . .

# Build the React/Vite app
RUN npm run build

# ---------- runtime stage ----------
FROM nginx:stable-alpine

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Optionally, provide a custom nginx configuration to handle React router (SPA)
# By default, nginx will just serve static files. To handle client-side routing,
# we add a simple fallback to index.html.
RUN echo 'server { \
    listen 80; \
    location / { \
        root   /usr/share/nginx/html; \
        index  index.html index.htm; \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
