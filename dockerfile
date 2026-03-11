FROM python:3.11-slim

WORKDIR /app

COPY THIRD_PARTY_LICENSES /licenses/THIRD_PARTY_LICENSES
COPY LICENSE /licenses/LICENSE
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

EXPOSE 5089

ENTRYPOINT ["/app/install_scripts/entrypoint.sh"]

CMD ["python","api.py"]
