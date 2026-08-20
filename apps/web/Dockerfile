FROM node:22-alpine AS build
ENV BUILD_STANDALONE=true
ARG FOUNDATION_API_URL=http://127.0.0.1:8001
ARG AUTOMATION_HOST_URL=http://127.0.0.1:8765
ENV FOUNDATION_API_URL=${FOUNDATION_API_URL}
ENV AUTOMATION_HOST_URL=${AUTOMATION_HOST_URL}
RUN corepack enable
WORKDIR /workspace
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --filter @careeros/web... --no-frozen-lockfile
COPY apps/web apps/web
RUN pnpm --dir apps/web build
FROM node:22-alpine
COPY --from=build /workspace/apps/web/.next/standalone ./
COPY --from=build /workspace/apps/web/.next/static ./apps/web/.next/static
WORKDIR /apps/web
EXPOSE 3000
CMD ["node", "server.js"]
