FROM python:3.12-slim
WORKDIR /app
COPY app/ app/
COPY public/ public/
# optional: enables Claude-assisted entity resolution if ANTHROPIC_API_KEY is set
RUN pip install --no-cache-dir anthropic
ENV BHARATWATCH_HOST=0.0.0.0
ENV BHARATWATCH_DB=/data/bharatwatch.db
VOLUME /data
EXPOSE 8787
CMD ["python3", "app/server.py"]
