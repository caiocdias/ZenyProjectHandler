FROM python:3.13.7-slim-bookworm@sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY requirements-server.lock ./
RUN python -m pip install setuptools==80.10.2 \
    && python -m pip wheel --wheel-dir=/wheels -r requirements-server.lock

COPY server/pyproject.toml ./server/pyproject.toml
COPY src/zeny_project_handler ./src/zeny_project_handler
COPY src/zeny_project_handler_contracts ./src/zeny_project_handler_contracts
COPY src/zeny_project_handler_server ./src/zeny_project_handler_server
RUN python -m pip wheel --no-deps --no-build-isolation --wheel-dir=/wheels ./server


FROM python:3.13.7-slim-bookworm@sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends tesseract-ocr tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 zeny \
    && useradd --uid 10001 --gid zeny --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin zeny \
    && install --directory --owner=zeny --group=zeny /data /app

WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements-server.lock ./
RUN python -m pip install --no-index --find-links=/wheels -r requirements-server.lock \
    && python -m pip install --no-deps /wheels/zeny_project_handler_server-*.whl \
    && rm -rf /wheels requirements-server.lock \
    && find /usr/local/lib/python3.13/site-packages -type d -name __pycache__ -prune -exec rm -rf '{}' +

USER 10001:10001
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=12 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).read()"]

CMD ["python", "-m", "zeny_project_handler_server"]
