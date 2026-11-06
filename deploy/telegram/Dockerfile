FROM soulter/astrbot:v4.29.4
# One pinned read-only search dependency; no extra service or daemon.
COPY plugin/astrbot_plugin_dafeiyu_local_life/requirements.txt /tmp/dafeiyu-requirements.txt
COPY deploy/telegram/requirements-livingmemory.txt /tmp/livingmemory-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/dafeiyu-requirements.txt -r /tmp/livingmemory-requirements.txt \
    && rm /tmp/dafeiyu-requirements.txt /tmp/livingmemory-requirements.txt
