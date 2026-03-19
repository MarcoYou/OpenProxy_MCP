"""Step 3 Check: 종목코드/회사명으로 소집공고 검색 + 본문"""

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")

from open_proxy_mcp.dart.client import DartClient


async def main():
    client = DartClient()

    # 1) 종목코드로 기업 조회
    print("=== 종목코드 033780 조회 ===\n")
    corp = await client.lookup_corp_code("033780")
    print(f"  corp_code: {corp['corp_code']}")
    print(f"  회사명: {corp['corp_name']}")
    print(f"  종목코드: {corp['stock_code']}")
    print()

    # 2) 회사명으로도 조회
    print("=== 회사명 'KT&G' 조회 ===\n")
    corp2 = await client.lookup_corp_code("KT&G")
    if corp2:
        print(f"  corp_code: {corp2['corp_code']}")
        print(f"  회사명: {corp2['corp_name']}")
        print(f"  종목코드: {corp2['stock_code']}")
    else:
        print("  못 찾음")
    print()

    # 3) ticker로 소집공고 검색
    print("=== 033780 소집공고 검색 ===\n")
    result = await client.search_filings_by_ticker(
        ticker="033780",
        bgn_de="20260101",
        end_de="20260319",
        pblntf_ty="E",
    )

    corp_info = result.get("corp_info", {})
    print(f"  검색 기업: {corp_info.get('corp_name')} ({corp_info.get('stock_code')})")
    print(f"  총 건수: {result['total_count']}")

    filings = [item for item in result.get("list", []) if "소집" in item.get("report_nm", "")]
    print(f"  소집공고: {len(filings)}건\n")

    for item in filings:
        print(f"    {item['report_nm']} | {item['rcept_dt']}")

    # 4) 본문 일부 가져오기
    if filings:
        print(f"\n=== 본문 미리보기 ===\n")
        text = await client.get_document(filings[0]["rcept_no"])
        print(f"  전체 길이: {len(text):,}자")
        print(f"\n{text[:1000]}")


asyncio.run(main())
