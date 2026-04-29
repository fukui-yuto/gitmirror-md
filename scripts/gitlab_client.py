"""python-gitlab の薄ラッパー: 認証・リトライ処理."""

import functools
import logging
import os
import time

import gitlab

logger = logging.getLogger(__name__)

# リトライ設定
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0  # seconds


def retry_on_rate_limit(func):
    """429 / 5xx に対し指数バックオフで最大5回リトライするデコレータ."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except gitlab.exceptions.GitlabHttpError as e:
                if e.response_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                    wait = INITIAL_BACKOFF * (2**attempt)
                    logger.warning(
                        "API error %d, retrying in %.1fs (attempt %d/%d)",
                        e.response_code,
                        wait,
                        attempt + 1,
                        MAX_RETRIES,
                    )
                    time.sleep(wait)
                else:
                    raise

    return wrapper


def get_project() -> "gitlab.v4.objects.Project":
    """環境変数から GitLab プロジェクトオブジェクトを取得する."""
    url = os.environ["GITLAB_URL"]
    token = os.environ["SYNC_TOKEN"]
    project_id = os.environ["CI_PROJECT_ID"]

    gl = gitlab.Gitlab(url, private_token=token)
    gl.auth()
    return gl.projects.get(project_id)
