# syntax=docker/dockerfile:1@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32

FROM python:3.13.7-slim-bookworm@sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d AS builder

ARG SOURCE_DATE_EPOCH=315532800

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}

WORKDIR /build
COPY requirements-server.lock ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install setuptools==80.10.2 \
    && python -m pip wheel --wheel-dir=/wheels -r requirements-server.lock

COPY server/pyproject.toml ./server/pyproject.toml
COPY src/zeny_project_handler ./src/zeny_project_handler
COPY src/zeny_project_handler_contracts ./src/zeny_project_handler_contracts
COPY src/zeny_project_handler_server ./src/zeny_project_handler_server
RUN python -m pip wheel --no-deps --no-build-isolation --wheel-dir=/wheels ./server


FROM python:3.13.7-slim-bookworm@sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d AS runtime

ARG ZENY_RELEASE_VERSION=0.3.0

LABEL org.opencontainers.image.title="Zeny Project Handler Server" \
    org.opencontainers.image.version="${ZENY_RELEASE_VERSION}" \
    org.opencontainers.image.description="Servidor protegido do Zeny Project Handler"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    DEBIAN_FRONTEND=noninteractive apt-get update \
    && python -c "import urllib.request; urllib.request.urlretrieve('https://packages.microsoft.com/debian/12/prod/pool/main/p/packages-microsoft-prod/packages-microsoft-prod_1.1-debian12_all.deb', '/tmp/packages-microsoft-prod.deb')" \
    && echo "8434dcb8c346dc95fbd63dbece056c343704590b58b6a5c323d39acf52bf0b48  /tmp/packages-microsoft-prod.deb" | sha256sum --check - \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
        msodbcsql18=18.6.2.1-1 unixodbc=2.3.11-2+deb12u1 \
    && apt-get install --yes --no-install-recommends \
        -o APT::Keep-Downloaded-Packages=true tesseract-ocr tesseract-ocr-por \
    && groupadd --gid 10001 zeny \
    && useradd --uid 10001 --gid zeny --no-create-home --no-log-init --home-dir /nonexistent --shell /usr/sbin/nologin zeny \
    && install --directory --owner=zeny --group=zeny /data /app \
    && find /var/cache -mindepth 1 -maxdepth 1 ! -name apt -exec rm -rf '{}' + \
    && find /var/log /tmp /var/tmp -mindepth 1 -delete \
    && rm -rf /root/.cache

WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements-server.lock ./
RUN python -m pip install --no-index --find-links=/wheels -r requirements-server.lock \
    && python -m pip install --no-deps /wheels/zeny_project_handler_server-*.whl \
    && rm -rf /wheels requirements-server.lock \
    && find /usr/local/lib/python3.13/site-packages -type d -name __pycache__ -prune -exec rm -rf '{}' + \
    && find /var/cache /var/log /tmp /var/tmp -mindepth 1 -delete \
    && rm -rf /root/.cache

USER 10001:10001
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=12 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).read()"]

CMD ["python", "-m", "zeny_project_handler_server"]
