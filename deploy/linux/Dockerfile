FROM python:3.12-slim-bookworm AS app
ENV HOME=/data PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 \
    LINUXDO_CACHE_DIR=/data LINUXDO_READ_BROWSER=0 LINUXDO_MCP_TOKEN_FILE=/data/mcp-token
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 linuxdo && useradd --uid 10001 --gid 10001 --no-create-home linuxdo \
    && mkdir /data && chown 10001:10001 /data && chmod 700 /data
COPY deploy/linux/constraints.txt /tmp/constraints.txt
RUN pip install --no-cache-dir -r /tmp/constraints.txt hatchling
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps --no-build-isolation . && pip check
USER 10001:10001
VOLUME ["/data"]
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/healthz',timeout=2).close()"
CMD ["python", "-m", "linuxdo_mcp.http_server"]

FROM app AS tunnel
USER root
ARG TARGETARCH
COPY deploy/linux/install_tunnel.py /tmp/install_tunnel.py
RUN python /tmp/install_tunnel.py "$TARGETARCH" && rm /tmp/install_tunnel.py
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/readyz',timeout=2).close()"
CMD ["tunnel-client", "run", "--config", "/data/tunnel.json"]
