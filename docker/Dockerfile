FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && PIP_ONLY_BINARY=pandas,numpy pip install --no-cache-dir -r requirements.txt

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
