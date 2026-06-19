import os
import logging
import json
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from app.config import settings

class GCPJSONFormatter(logging.Formatter):
    """GCP Cloud Logging 호환 JSON 포맷터"""
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "logging.googleapis.com/sourceLocation": {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
            }
        }
        
        # Exception Traceback이 있을 경우 추가
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        # extra 변수로 들어오는 값을 JSON 필드로 직접 포함
        for key, val in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process"
            ):
                log_data[key] = val
                
        return json.dumps(log_data, ensure_ascii=False)

def setup_logger(name: str = "vision_rag") -> logging.Logger:
    """
    애플리케이션 전역에서 공통으로 사용할 로거를 설정합니다.
    
    - 콘솔(StreamHandler)과 일별 회전 파일(TimedRotatingFileHandler)에 로그를 출력합니다.
    - 프로덕션(Cloud Run) 환경의 경우 콘솔 출력을 GCP 호환 JSON 구조로 출력합니다.
    - 로그 파일은 settings.LOG_DIR 디렉토리에 저장됩니다.
    """
    logger = logging.getLogger(name)
    
    # 이미 핸들러가 구성되어 있다면 중복 방지를 위해 기존 로거 반환
    if logger.handlers:
        return logger
        
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # 💡 프로덕션(GCP Cloud Run)일 때 콘솔 출력을 JSON으로 구조화
    use_json = os.environ.get("LOG_FORMAT_JSON", "false").lower() == "true" or not settings.USE_LOCAL_STORAGE
    
    # 로그 포맷 정의 (한국어 로그 해석 및 파싱 최적화)
    text_format = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 1. 콘솔 핸들러 추가
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    if use_json:
        console_handler.setFormatter(GCPJSONFormatter())
    else:
        console_handler.setFormatter(text_format)
    logger.addHandler(console_handler)
    
    # 2. 파일 핸들러 추가 (TimedRotatingFileHandler) - 파일은 항상 예쁜 텍스트로 보관
    log_dir = settings.LOG_DIR
    if not os.path.isabs(log_dir):
        # 실행 디렉토리 기준 절대 경로로 설정
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        log_dir = os.path.join(base_dir, log_dir)
        
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
        
    log_file_path = os.path.join(log_dir, "vision_rag.log")
    
    # 자정(midnight)에 회전, 1일 간격, 최대 30일 보관
    file_handler = TimedRotatingFileHandler(
        log_file_path,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(text_format)
    logger.addHandler(file_handler)
    
    return logger

# 전역 로거 인스턴스 정의
logger = setup_logger()
