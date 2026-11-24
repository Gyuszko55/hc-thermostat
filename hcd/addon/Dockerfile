ARG BUILD_FROM
FROM ${BUILD_FROM}

# 0.1.3 (security review): fixed versions; an unprivileged user for the service (run.sh drops to it)
RUN apk add --no-cache python3 py3-pip tzdata su-exec \
 && adduser -D -H -s /sbin/nologin hcd \
 && python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir "aiohttp==3.14.4" "pyyaml==6.0.3" "aiomqtt==2.5.1"

# the decision core and the service, copied in by tools/build_hcd_addon.sh
COPY hc_core /opt/hcd/hc_core
COPY hcd /opt/hcd/hcd
COPY run.sh /run.sh
RUN chmod a+x /run.sh

ENV PYTHONPATH=/opt/hcd PYTHONUNBUFFERED=1
CMD ["/run.sh"]
