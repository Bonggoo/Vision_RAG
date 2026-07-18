"""
GCS 버킷의 플랫 구조를 사용자별 디렉터리 구조로 마이그레이션하는 스크립트.

기존 구조:  {uuid}/metadata.json, {uuid}/original.pdf, ...
새 구조:    users/{email}/{uuid}/metadata.json, users/{email}/{uuid}/original.pdf, ...

사용법:
    # 미리보기 (dry-run, 기본값)
    python migrate_gcs_structure.py --default-owner bonggoo@gmail.com

    # 실제 실행
    python migrate_gcs_structure.py --default-owner bonggoo@gmail.com --execute
"""
import sys
import json
import argparse
from google.cloud import storage
from app.config import settings


def _resolve_owner_email(metadata: dict, default_owner: str) -> str:
    """
    메타데이터에서 소유자 이메일을 추출합니다.
    owner_email이 없거나 빈 문자열이면 기본 소유자를 반환합니다.
    이메일은 항상 소문자로 정규화합니다.
    """
    email = metadata.get("owner_email", "").strip()
    if not email:
        email = default_owner
    return email.lower()


def _build_new_prefix(owner_email: str, doc_uuid: str) -> str:
    """새 GCS 경로 프리픽스를 생성합니다. (예: users/bonggoo@gmail.com/abc-123/)"""
    return f"users/{owner_email}/{doc_uuid}/"


def migrate_gcs_structure(default_owner: str, execute: bool = False) -> dict:
    """
    GCS 버킷의 플랫 구조를 사용자별 디렉터리 구조로 마이그레이션합니다.

    Args:
        default_owner: owner_email이 없는 문서에 사용할 기본 소유자 이메일
        execute: True이면 실제 마이그레이션 수행, False이면 미리보기만

    Returns:
        마이그레이션 결과 요약 딕셔너리 (성공, 스킵, 오류 건수)
    """
    client = storage.Client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)

    # --- 1단계: 기존 metadata.json 목록 수집 ---
    print(f"\n🔍 버킷 '{settings.GCS_BUCKET_NAME}'에서 문서 검색 중...")
    all_meta_blobs = list(bucket.list_blobs(match_glob="*/metadata.json"))
    print(f"📋 총 {len(all_meta_blobs)}개 metadata.json 발견")

    mode_label = "🚀 실행 모드" if execute else "👀 미리보기 모드 (dry-run)"
    print(f"{mode_label}")
    print(f"👤 기본 소유자: {default_owner.lower()}")
    print("=" * 70)

    # --- 결과 카운터 ---
    stats = {"success": 0, "skipped": 0, "error": 0}

    for meta_blob in all_meta_blobs:
        # blob 이름에서 문서 UUID 추출 (예: "abc-123/metadata.json" → "abc-123")
        blob_parts = meta_blob.name.split("/")

        # 이미 users/ 프리픽스로 시작하는 blob은 스킵 (이미 마이그레이션됨)
        if meta_blob.name.startswith("users/"):
            print(f"  ⏭️  [스킵] {meta_blob.name} (이미 마이그레이션됨)")
            stats["skipped"] += 1
            continue

        doc_uuid = blob_parts[0]

        try:
            # --- 2단계: metadata.json 다운로드 및 소유자 이메일 확인 ---
            content = meta_blob.download_as_text()
            metadata = json.loads(content)
            owner_email = _resolve_owner_email(metadata, default_owner)
            filename = metadata.get("filename", "알 수 없음")

            new_prefix = _build_new_prefix(owner_email, doc_uuid)
            old_prefix = f"{doc_uuid}/"

            print(f"\n  📄 문서: {filename} (UUID: {doc_uuid})")
            print(f"     소유자: {owner_email}")
            print(f"     이동: {old_prefix}  →  {new_prefix}")

            # --- 3단계: 해당 문서의 모든 blob 열거 ---
            doc_blobs = list(bucket.list_blobs(prefix=old_prefix))
            print(f"     파일 수: {len(doc_blobs)}개")

            if not execute:
                # 미리보기 모드: 이동 대상 파일 목록만 출력
                for blob in doc_blobs:
                    old_name = blob.name
                    # 기존 프리픽스를 새 프리픽스로 교체
                    relative_path = old_name[len(old_prefix):]
                    new_name = f"{new_prefix}{relative_path}"
                    print(f"       {old_name}  →  {new_name}")
                stats["success"] += 1
                continue

            # --- 4단계: 실제 마이그레이션 (copy-then-delete) ---
            # metadata.json은 gcs_prefix 필드를 추가한 뒤 별도 처리
            migrated_blobs = []

            for blob in doc_blobs:
                old_name = blob.name
                relative_path = old_name[len(old_prefix):]
                new_name = f"{new_prefix}{relative_path}"

                if relative_path == "metadata.json":
                    # metadata.json: gcs_prefix 필드 추가 후 새 위치에 업로드
                    metadata["gcs_prefix"] = new_prefix
                    updated_content = json.dumps(metadata, ensure_ascii=False, indent=2)
                    new_blob = bucket.blob(new_name)
                    new_blob.upload_from_string(
                        updated_content,
                        content_type="application/json",
                    )
                    # 새 blob이 정상적으로 존재하는지 확인
                    if new_blob.exists():
                        migrated_blobs.append((blob, new_name))
                        print(f"       ✅ {old_name}  →  {new_name} (gcs_prefix 추가)")
                    else:
                        raise RuntimeError(f"복사 검증 실패: {new_name}")
                else:
                    # 일반 파일: copy_blob으로 복사
                    new_blob = bucket.copy_blob(blob, bucket, new_name)
                    # 복사된 blob 존재 확인
                    if bucket.blob(new_name).exists():
                        migrated_blobs.append((blob, new_name))
                        print(f"       ✅ {old_name}  →  {new_name}")
                    else:
                        raise RuntimeError(f"복사 검증 실패: {new_name}")

            # --- 5단계: 모든 파일 복사 성공 후 원본 삭제 ---
            for old_blob, new_name in migrated_blobs:
                old_blob.delete()
                print(f"       🗑️  원본 삭제: {old_blob.name}")

            stats["success"] += 1
            print(f"     ✅ 문서 마이그레이션 완료")

        except Exception as e:
            # 에러 발생 시 해당 문서만 스킵하고 계속 진행
            print(f"     ❌ 오류 발생 (스킵): {e}")
            stats["error"] += 1
            continue

    # --- 결과 요약 ---
    print("\n" + "=" * 70)
    print("📊 마이그레이션 결과 요약")
    print(f"   ✅ 성공: {stats['success']}건")
    print(f"   ⏭️  스킵: {stats['skipped']}건 (이미 마이그레이션됨)")
    print(f"   ❌ 오류: {stats['error']}건")
    print("=" * 70)

    if not execute and stats["success"] > 0:
        print(
            "\n💡 실제 마이그레이션을 실행하려면 --execute 플래그를 추가하세요."
        )
        print(
            f"   예: python migrate_gcs_structure.py "
            f"--default-owner {default_owner} --execute"
        )

    return stats


def main():
    """커맨드라인 진입점."""
    parser = argparse.ArgumentParser(
        description="GCS 버킷의 플랫 구조를 사용자별 디렉터리 구조로 마이그레이션합니다.",
    )
    parser.add_argument(
        "--default-owner",
        required=True,
        help="owner_email이 없는 문서에 사용할 기본 소유자 이메일",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="실제 마이그레이션을 수행합니다 (기본값: dry-run 미리보기)",
    )
    args = parser.parse_args()

    # 이메일 정규화
    default_owner = args.default_owner.strip().lower()
    if not default_owner or "@" not in default_owner:
        print("❌ 유효한 이메일 주소를 입력하세요.")
        sys.exit(1)

    print("🚀 GCS 구조 마이그레이션 시작")
    print(f"   버킷: {settings.GCS_BUCKET_NAME}")
    print(f"   기본 소유자: {default_owner}")
    print(f"   모드: {'실행' if args.execute else '미리보기 (dry-run)'}")

    if args.execute:
        # 실제 실행 전 확인 프롬프트
        confirm = input("\n⚠️  실제 마이그레이션을 수행합니다. 계속하시겠습니까? (y/N): ")
        if confirm.strip().lower() != "y":
            print("❌ 마이그레이션이 취소되었습니다.")
            sys.exit(0)

    stats = migrate_gcs_structure(default_owner, execute=args.execute)

    if args.execute and stats["success"] > 0:
        print(f"\n✅ 마이그레이션 완료! {stats['success']}건의 문서가 이동되었습니다.")
    elif stats["success"] == 0 and stats["error"] == 0:
        print("\n✅ 마이그레이션할 문서가 없습니다.")


if __name__ == "__main__":
    main()
