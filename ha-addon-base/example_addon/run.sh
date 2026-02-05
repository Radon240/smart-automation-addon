#!/usr/bin/with-contenv bashio

echo "[diploma_addon] Starting Python Flask ML service..."
python3 /app/main.py > /proc/1/fd/1 2>&1 &
PYTHON_PID=$!
echo "[diploma_addon] Python Flask service PID: $PYTHON_PID"

# Даём Python сервису время на старт
echo "[diploma_addon] Waiting for Python Flask service to start..."
sleep 3

echo "[diploma_addon] Starting .NET web application..."
dotnet /app/dotnet_out/DiplomaAddon.dll
DOTNET_PID=$!

# Ждём обоих процессов
wait $PYTHON_PID $DOTNET_PID
