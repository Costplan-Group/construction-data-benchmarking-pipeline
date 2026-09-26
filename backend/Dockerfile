# Backend API image: Python 3.13 + ODBC Driver 18 + mssql-tools18 + WeasyPrint libs.
# Build from repo root: docker build -f backend/Dockerfile .

FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/mssql-tools18/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gnupg2 \
        apt-transport-https \
        ca-certificates \
        unixodbc \
        unixodbc-dev \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
        fonts-dejavu-core \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 mssql-tools18 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY ingestion_engine ./ingestion_engine
COPY branding.example.yaml ./branding.example.yaml
COPY database ./database

COPY backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh \
        /app/database/docker/apply_schema.sh \
        /app/database/docker/db-init.sh \
    && chmod +x /docker-entrypoint.sh \
        /app/database/docker/apply_schema.sh \
        /app/database/docker/db-init.sh

EXPOSE 8001

ENTRYPOINT ["/docker-entrypoint.sh"]
