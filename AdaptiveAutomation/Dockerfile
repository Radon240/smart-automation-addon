ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip

RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

WORKDIR /app
COPY app/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/
COPY run.sh /
RUN chmod +x /run.sh

CMD ["/run.sh"]
