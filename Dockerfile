FROM python:3.12-slim
WORKDIR /app
COPY . .
ENV LUMA_HOST=0.0.0.0
ENV PORT=4173
EXPOSE 4173
CMD ["python3", "server.py"]
