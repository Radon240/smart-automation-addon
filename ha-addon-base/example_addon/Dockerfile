ARG BUILD_FROM
FROM ${BUILD_FROM}

# Базовые зависимости: Python + .NET SDK
RUN apk add --no-cache \
    python3 \
    py3-pip \
    python3-dev \
    build-base \
    icu-libs \
    libgcc \
    libstdc++ \
    dotnet8-sdk

# Сборка .NET-приложения
WORKDIR /src
COPY app/dotnet/ ./dotnet/
RUN dotnet publish ./dotnet/DiplomaAddon.csproj -c Release -o /app/dotnet_out

# Python-зависимости
WORKDIR /app
COPY app/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Остальной код и скрипт запуска
COPY app/ /app/
COPY run.sh /
RUN chmod +x /run.sh

CMD ["/run.sh"]