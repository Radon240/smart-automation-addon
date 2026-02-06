ARG BUILD_FROM
FROM ${BUILD_FROM}

# Базовые зависимости
RUN apk add --no-cache \
    python3 \
    py3-pip \
    python3-dev \
    build-base \
    icu-libs \
    libgcc \
    libstdc++ \
    dotnet8-sdk

# ---------- Python venv ----------
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Python-зависимости
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ---------- .NET build ----------
WORKDIR /src
COPY app/dotnet/ ./dotnet/
RUN dotnet publish ./dotnet/DiplomaAddon.csproj -c Release -o /app/dotnet_out

# ---------- App files ----------
COPY app/ /app/
COPY run.sh /
RUN chmod +x /run.sh

CMD ["/run.sh"]
