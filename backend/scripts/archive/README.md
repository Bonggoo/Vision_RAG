# 아카이브된 일회성 마이그레이션 스크립트

이 디렉토리의 스크립트들은 **이미 완료된 일회성 마이그레이션**입니다.
현재 GCS 구조(`users/{email}/{uuid}/...`)에서 재실행하면 데이터가 손상될 수 있으므로 실행하지 마세요.

- `migrate_gcs_structure.py` — 레거시 평면 구조(`{uuid}/...`) → 사용자별 구조 이전 (완료)
- `migrate_owner_email.py` — 문서 메타데이터에 owner_email 필드 부여 (완료)
- `fix_metadata_filenames.py` — 메타데이터 filename 필드 정규화 (완료)
