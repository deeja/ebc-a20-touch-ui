# Just enough to run the Tk app as an X client - no X server of its own.
# deploy/test-local-ui.sh forwards this container's display to the host's
# already-running X server, so this only needs the app's own runtime deps.
FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3-tk python3-serial && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
