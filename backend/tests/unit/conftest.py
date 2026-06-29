"""
pytest 공통 픽스처.
GCS/Gemini 환경변수를 더미로 설정하여 import 시 연결 시도를 차단합니다.
"""
import os
import pytest

os.environ.setdefault("GCS_BUCKET_NAME", "test-bucket")
os.environ.setdefault("GEMINI_API_KEY", "dummy-key")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "dummy")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "dummy")
os.environ.setdefault("JWT_SECRET_KEY", "dummy-secret-for-tests")
os.environ.setdefault("PDF_UPLOAD_DIR", "/tmp/test-uploads")
os.environ.setdefault("USE_LOCAL_STORAGE", "True")
