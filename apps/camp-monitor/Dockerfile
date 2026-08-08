FROM mcr.microsoft.com/playwright/python:v1.54.0-noble

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY camp_monitor.py ./

USER pwuser

ENTRYPOINT ["python", "/app/camp_monitor.py"]
CMD ["--config", "/config/config.json"]

