FROM soulter/astrbot:v4.29.4
# One pinned read-only search dependency; no extra service or daemon.
COPY plugin/astrbot_plugin_dafeiyu_local_life/requirements.txt /tmp/dafeiyu-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/dafeiyu-requirements.txt \
    && rm /tmp/dafeiyu-requirements.txt
