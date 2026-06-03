"""
레거시 문서에 owner_email을 일괄 배정하는 마이그레이션 스크립트.

사용법:
    python migrate_owner_email.py <owner_email>
    예: python migrate_owner_email.py bonggoo@gmail.com
"""
import sys
import json
from google.cloud import storage
from app.config import settings
from app.utils.logger import logger


def migrate_owner_email(default_owner: str, dry_run: bool = False) -> int:
    """
    GCS 버킷의 모든 metadata.json을 순회하여,
    owner_email이 없는 레거시 문서에 기본 소유자를 배정합니다.
    
    Args:
        default_owner: 배정할 이메일 주소
        dry_run: True이면 실제 수정 없이 대상만 출력
    
    Returns:
        마이그레이션된 문서 수
    """
    client = storage.Client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blobs = list(bucket.list_blobs(match_glob="*/metadata.json"))
    
    print(f"\n📋 총 {len(blobs)}개 문서 메타데이터 발견")
    print(f"🎯 대상: owner_email이 없는 레거시 문서")
    print(f"👤 배정할 소유자: {default_owner}")
    if dry_run:
        print("🔍 DRY RUN 모드 (실제 수정 없음)\n")
    print("-" * 60)
    
    migrated = 0
    skipped = 0
    errors = 0
    
    for blob in blobs:
        try:
            content = blob.download_as_text()
            meta = json.loads(content)
            
            filename = meta.get("filename", "알 수 없음")
            current_owner = meta.get("owner_email")
            
            # 레거시: owner_email 없음, 빈 값, 또는 로컬개발 더미 값
            LEGACY_OWNERS = {None, "", "local-dev@visionrag.app"}
            if current_owner in LEGACY_OWNERS:
                if dry_run:
                    print(f"  🔄 [대상] {filename} → {default_owner}")
                else:
                    meta["owner_email"] = default_owner
                    blob.upload_from_string(
                        json.dumps(meta, ensure_ascii=False, indent=2),
                        content_type="application/json"
                    )
                    print(f"  ✅ {filename} → {default_owner}")
                migrated += 1
            else:
                print(f"  ⏭️  {filename} (기존 소유자: {current_owner})")
                skipped += 1
                
        except Exception as e:
            print(f"  ❌ {blob.name} 처리 실패: {e}")
            errors += 1
    
    print("-" * 60)
    print(f"\n📊 결과: 마이그레이션 {migrated}건 | 스킵 {skipped}건 | 오류 {errors}건")
    
    if dry_run and migrated > 0:
        print(f"\n💡 실제 적용하려면 --dry-run 없이 다시 실행하세요.")
    
    return migrated


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python migrate_owner_email.py <owner_email> [--dry-run]")
        print("  예: python migrate_owner_email.py bonggoo@gmail.com")
        print("  예: python migrate_owner_email.py bonggoo@gmail.com --dry-run")
        sys.exit(1)
    
    owner_email = sys.argv[1]
    dry_run = "--dry-run" in sys.argv
    
    print(f"\n🚀 레거시 문서 owner_email 마이그레이션 시작")
    result = migrate_owner_email(owner_email, dry_run=dry_run)
    
    if result > 0 and not dry_run:
        print(f"\n✅ 마이그레이션 완료! {result}건의 문서에 소유자가 배정되었습니다.")
    elif result == 0:
        print(f"\n✅ 마이그레이션할 레거시 문서가 없습니다.")
