FROM python:3.12-alpine@sha256:e064671ca452259bab50e8e2c7bd896e39e9a343bb06ca25234adf6fe18d0fc7
COPY relay.py /app/relay.py
USER 65534:65534
CMD ["python", "-u", "/app/relay.py"]
