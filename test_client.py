"""Step 2 Check: DartClient로 주주총회소집공고 검색 테스트"""

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")

from open_proxy_mcp.dart.client import DartClient


async def main():
    client = DartClient()

    # 기타공시(E)에서 주주총회소집공고 검색
    result = await client.search_filings(
        bgn_de="20260201",
        end_de="20260319",
        pblntf_ty="E",
    )

    print(f"총 건수: {result['total_count']}")

    # "소집" 포함 건만 필터
    filings = [item for item in result["list"] if "소집" in item.get("report_nm", "")]
    print(f"주주총회소집공고: {len(filings)}건")
    print()

    for item in filings[:5]:
        print(f"  {item['corp_name']} | {item['report_nm']} | {item['rcept_dt']}")


asyncio.run(main())
