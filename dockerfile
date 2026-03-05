FROM node:24

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip python3.11-venv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
COPY install_scripts /app/install_scripts
RUN chmod +x -R /app/install_scripts
COPY src /app/src
COPY config /app/config
COPY guesslang /app/guesslang
COPY api.py .

RUN mkdir /app/temp
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip3 install --no-cache-dir -r requirements.txt

EXPOSE 5000

ENTRYPOINT ["/app/install_scripts/entrypoint.sh"]

CMD ["python","api.py"]
