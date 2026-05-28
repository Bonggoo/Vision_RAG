class DuplicateDocumentError(Exception):
    """동일한 파일이 이미 업로드되어 있을 때 발생"""
    def __init__(self, existing_filename: str):
        super().__init__(f"동일한 파일이 이미 업로드되어 있습니다: {existing_filename}")
        self.existing_filename = existing_filename

class EmptyFileError(Exception):
    """파일 크기가 0바이트일 때 발생"""
    def __init__(self):
        super().__init__("파일이 로컬에 저장되어 있지 않거나 손상되었습니다. 파일을 확인한 후 다시 시도해 주세요.")
