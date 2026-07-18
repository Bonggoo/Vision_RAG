class DuplicateDocumentError(Exception):
    """동일한 파일이 이미 업로드되어 있을 때 발생"""
    def __init__(self, existing_filename: str):
        super().__init__(f"동일한 파일이 이미 업로드되어 있습니다: {existing_filename}")
        self.existing_filename = existing_filename

class EmptyFileError(Exception):
    """파일 크기가 0바이트일 때 발생"""
    def __init__(self):
        super().__init__("파일이 로컬에 저장되어 있지 않거나 손상되었습니다. 파일을 확인한 후 다시 시도해 주세요.")

class FileTooLargeError(Exception):
    """업로드 파일이 허용 크기를 초과할 때 발생"""
    def __init__(self, max_mb: int):
        super().__init__(f"파일이 너무 큽니다. 최대 {max_mb}MB까지 업로드할 수 있습니다.")
        self.max_mb = max_mb

class TooManyPagesError(Exception):
    """PDF 페이지 수가 허용 상한을 초과할 때 발생"""
    def __init__(self, max_pages: int):
        super().__init__(f"페이지가 너무 많습니다. 최대 {max_pages}페이지까지 처리할 수 있습니다.")
        self.max_pages = max_pages
