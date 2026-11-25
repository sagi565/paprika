# wacli: the WhatsApp CLI that sends invoices from the business's own number
# (https://github.com/openclaw/wacli). Pinned to a release and checked against its SHA-256.
FROM python:3.12-slim AS wacli
ARG WACLI_VERSION=0.26.1
ARG WACLI_SHA256=515405c5a33c7f651a368484740db662736f50c275be5a0504fb0a84dce47013
RUN python -c "import hashlib, sys, urllib.request; \
url = 'https://github.com/openclaw/wacli/releases/download/v${WACLI_VERSION}/wacli_${WACLI_VERSION}_linux_amd64.tar.gz'; \
data = urllib.request.urlopen(url, timeout=180).read(); \
digest = hashlib.sha256(data).hexdigest(); \
sys.exit('wacli checksum mismatch: ' + digest) if digest != '${WACLI_SHA256}' else None; \
open('/tmp/wacli.tgz', 'wb').write(data)" \
    && mkdir /tmp/wacli && tar -xzf /tmp/wacli.tgz -C /tmp/wacli \
    && install -m 0755 "$(find /tmp/wacli -type f -name wacli | head -n 1)" /usr/local/bin/wacli

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# DejaVu covers Hebrew glyphs (mock invoice renderer, Chromium). Chromium prints Grow's
# invoice when its link is a web page instead of a PDF.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core chromium \
    && rm -rf /var/lib/apt/lists/*

COPY --from=wacli /usr/local/bin/wacli /usr/local/bin/wacli
RUN wacli --version

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd --create-home app && mkdir -p /data/invoices /data/wacli && chown -R app /data
USER app

EXPOSE 8000
# Hosts like Render pass the port in $PORT.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips "*"
