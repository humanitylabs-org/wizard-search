FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY server.py setup.json openapi.json SETUP.md ./
COPY web ./web
ARG REVISION=development
LABEL org.opencontainers.image.source="https://github.com/humanitylabs-org/wizard-search" org.opencontainers.image.revision=$REVISION
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 WIZARD_SEARCH_BIND=0.0.0.0 WIZARD_SEARCH_BASE="" WIZARD_SEARCH_REVISION=$REVISION
USER 1000:1000
EXPOSE 9288
HEALTHCHECK --interval=15s --timeout=3s CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9288/api/health',timeout=2)"
CMD ["python3", "server.py"]
