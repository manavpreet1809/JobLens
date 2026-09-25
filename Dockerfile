FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip check \
    && useradd --create-home --uid 10001 talentscope

# Explicit copies keep local credentials and unrelated files out of the image.
COPY --chown=talentscope:talentscope src/ ./src/
COPY --chown=talentscope:talentscope db/ ./db/
COPY --chown=talentscope:talentscope tests/ ./tests/
COPY --chown=talentscope:talentscope scripts/ ./scripts/
COPY --chown=talentscope:talentscope .streamlit/config.toml ./.streamlit/config.toml
COPY --chown=talentscope:talentscope streamlit_app.py ./
USER talentscope
EXPOSE 8501
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=2)"
CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.headless=true", "--browser.gatherUsageStats=false"]
