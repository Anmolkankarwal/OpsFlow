FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json tsconfig.json vite.config.ts index.html ./
RUN npm ci
COPY src ./src
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
