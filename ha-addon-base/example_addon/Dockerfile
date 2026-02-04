ARG BUILD_FROM
FROM $BUILD_FROM

# Базовые зависимости: Python (на будущее) + .NET SDK/Runtime для web-приложения
RUN apk add --no-cache \
    python3 \
    py3-pip \
    icu-libs \
    libgcc \
    libstdc++ \
    dotnet8-sdk

# Сборка .NET-приложения
WORKDIR /src
COPY app/dotnet/ ./dotnet/
RUN dotnet publish ./dotnet/DiplomaAddon.csproj -c Release -o /app/dotnet_out

# Python-зависимости (пока не используются, но оставляем как основу под модели)
WORKDIR /app
COPY app/requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

# Остальной код и скрипт запуска
COPY app/ /app/
COPY run.sh /
RUN chmod +x /run.sh

CMD ["/run.sh"]
