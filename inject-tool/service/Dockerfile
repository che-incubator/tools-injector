FROM python:3.12-slim

WORKDIR /app

COPY inject-tool/service/server.py inject-tool/service/injector.py inject-tool/service/registry.json ./

EXPOSE 8080

CMD ["python3", "server.py"]
