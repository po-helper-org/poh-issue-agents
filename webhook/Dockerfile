FROM python:3.12-slim

WORKDIR /app
COPY webhook/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY webhook/ .
COPY shared/ /app/shared/
# Диагностика конфига запускается ВНУТРИ контейнера (docker compose exec webhook
# python scripts/diag.py): смысл в том, чтобы прочитать окружение сервиса, а не
# хоста. Без этой строки скрипта в образе просто нет.
COPY scripts/ /app/scripts/

ENV PYTHONPATH=/app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]
