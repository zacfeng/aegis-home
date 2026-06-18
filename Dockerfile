FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ripgrep ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "hermes-agent[messaging]" \
    caldav==1.3.9 \
    redis==5.0.8 \
    pytz==2024.1

# Seed config — copied to HERMES_HOME on every container start
COPY SOUL.md     /opt/hermes-seed/SOUL.md
COPY config.yaml /opt/hermes-seed/config.yaml
COPY plugins/    /opt/hermes-seed/plugins/

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV HERMES_HOME=/opt/hermes-data

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["hermes", "gateway"]
