FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent volume is mounted here in the cloud; auto-refresh on open.
ENV HC_DATA_DIR=/data
ENV AUTO_REFRESH=1

EXPOSE 8080

CMD ["streamlit", "run", "dashboard.py", \
     "--server.port=8080", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
