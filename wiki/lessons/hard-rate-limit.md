---
type: lesson
title: hard rate limit — DART 분당 1000회를 코드로 강제
context: treasury ralph 측정 중 두 차례 24h IP 차단 (2026-05-04~05)
date_learned: 2026-05-05
---

# DART rate limit hard rule 강제

## Context

DART OpenAPI 분당 1000회 한도 — 초과 시 client fingerprint level 24시간 차단. CLAUDE.md에 정책 명시되어 있었지만 실제 batch script에서 호출 수 estimation 안 함.

발생 사고:
- iter 8 (2026-05-04): KOSPI 100 회사 audit (concurrency 4) — 100 × ~10 호출 = ~1000 호출이 1-2분 안에 hit → 차단. 24h 측정 보류.
- iter 12 (2026-05-05): 차단 풀린 후 KOSPI 100 (concurrency 2) 재시도 — concurrency 낮춤만으론 부족 (총 호출 수가 한도). 다시 차단.

## Did

**진단**:
- ping 100% loss는 ICMP 차단 (방화벽 일반) — IP 차단 indicator 아님
- TLS handshake success 후 HTTP request에서 reset → server-level 차단 확인
- opendart.fss.or.kr (API)만 차단, dart.fss.or.kr (웹/본문)은 정상 — 서브도메인별 차단

**hard enforcement 코드** (`dart/client.py`):
```python
_API_RATE_LIMIT_PER_MINUTE = 900  # 1000 - 10% buffer

self._api_call_timestamps: collections.deque[float] = collections.deque()
self._api_rate_lock = asyncio.Lock()

async def _throttle_api(self):
    async with self._api_rate_lock:
        now = time.monotonic()
        # 60s 윈도우 안의 호출만 유지
        while self._api_call_timestamps and now - self._api_call_timestamps[0] > 60:
            self._api_call_timestamps.popleft()
        # 윈도우 가득 — oldest 만료까지 sleep
        if len(self._api_call_timestamps) >= _API_RATE_LIMIT_PER_MINUTE:
            wait = 60 - (now - self._api_call_timestamps[0]) + 0.05
            if wait > 0:
                logger.warning(f"[DART API] rate limit window full ({_API_RATE_LIMIT_PER_MINUTE}/min) — wait {wait:.1f}s")
                await asyncio.sleep(wait)
        # 최소 간격 (race 방지)
        ...
        self._api_call_timestamps.append(now)
```

**batch script 정책** (CLAUDE.md):
- 회사수 × 평균 호출수 estimate, > 900이면 batch split
- 측정 batch는 **최대 30 회사 단위**
- 100 회사 batch 필요 시: 30+30+30 partial × batch 사이 sleep 또는 fly machine (다른 IP)

audit script `--offset` arg 추가: 30 회사씩 batch + sequential output files.

## Improved

- **iter 13~15 모든 batch 안전 진행** — KOSPI 100 + KOSDAQ 50 = 150 회사 측정 중 차단 0회
- treasury ralph G2 100% 도달 (이전 측정 못해 ralph 보류 중이었음)
- rate limiter는 application 전체에 효과 — batch script 외 모든 호출도 자동 보호

## Trade-off

- **사용자 응답 약간 느려질 수 있음**: cap 근접 시 sleep 발생 (warning log). 다만 거의 발생 X (사용자 호출은 회사 1-2개 단위).
- **rolling window state는 process-level**: fly.io machine 재시작 시 reset. 다만 차단은 외부 (DART) state라 동일 효과.
- **batch script가 큰 측정 시 시간 길어짐**: 30 회사 단위 + 자연 sleep. 100 회사 측정 ~10-15분 (이전 동시 호출 ~3-5분).

## Takeaway

- **외부 hard limit은 코드로 강제해야**. CLAUDE.md / docs는 인지 보장 X — 잊거나 batch 자동화 시 위반.
- **rolling window가 정확** — 단순 min interval (`time.sleep(0.1)`)은 burst 제어 X (race condition).
- **차단 진단**: ping 결과 X, HTTP reset 패턴 + 서브도메인 비교 (`opendart.fss.or.kr` vs `dart.fss.or.kr`). 키 회전 무효 (IP/fingerprint level).
- **fly machine 우회 가능**: production endpoint는 다른 IP라 로컬 차단 시 검증 가능 (`fly ssh console -C "..."`).
- 사용자 명확한 정책 ("절대 위반 X")은 다층으로 보호: 코드 + memory + CLAUDE.md.

## 관련

- memory: `feedback_dart_openapi_rate_limit.md`
- CLAUDE.md hard rule 섹션
- commit: `45dc273` (rolling window rate limiter)
