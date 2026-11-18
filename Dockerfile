FROM ghcr.io/astral-sh/uv:0.11.16 AS uv
FROM python:3.13-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --extra api --no-dev --no-editable && groupadd -g 10001 eval && useradd -u 10001 -g eval eval
ARG EVAL_GIT_COMMIT
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 EVAL_GIT_COMMIT=${EVAL_GIT_COMMIT}
USER 10001:10001
CMD ["python", "-m", "llm_codegen_eval.serving.benchmark", "--help"]
