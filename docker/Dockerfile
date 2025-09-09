FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./

# Install build dependencies for asyncpg and other binary packages
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    python3-dev \
 && pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --prefer-binary -r requirements.txt \
 && apt-get remove -y build-essential gcc python3-dev \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

COPY . .
# Ensure bash is available and fix CRLF in entrypoint on Windows checkouts
RUN apt-get update \
 && apt-get install -y --no-install-recommends bash \
 && rm -rf /var/lib/apt/lists/* \
 && sed -i 's/\r$//' docker/entrypoint.sh \
 && chmod +x docker/entrypoint.sh

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

ENTRYPOINT ["./docker/entrypoint.sh"]
