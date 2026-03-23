커밋, 푸시, documentation 업데이트를 수행합니다.

## 절차

1. `git status`와 `git diff --stat`으로 변경 사항 확인
2. 변경 있으면:
   - 적절한 커밋 메시지 작성 (한국어, 컨벤션: feat/fix/docs/chore)
   - `Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>` 포함
   - git add → commit → push
3. OpenProxy 서브모듈 변경 있으면:
   - `cd OpenProxy` → 서브모듈 커밋/푸시
   - **반드시 `cd /Users/marcoyou/Projects/open-proxy-mcp`로 돌아온 후** 부모 레포에서 `git add OpenProxy` → 커밋/푸시
4. `DEVLOG.md` 업데이트:
   - 오늘 날짜 섹션 없으면 생성
   - 방금 한 작업 내용 추가 (이미 기록된 내용은 중복 안 함)
5. `TO_DO.md` 업데이트:
   - 완료된 항목 체크 (`[x]`)
   - 새로 발견된 할 일 추가
6. docs 변경 있으면 추가 커밋 → 푸시

## 규칙
- 커밋 메시지는 변경 내용을 정확히 반영
- `.env`, credentials 등 민감 파일 절대 커밋 안 함
- 변경 없으면 빈 커밋 하지 않음
- DART API 호출하지 않음
