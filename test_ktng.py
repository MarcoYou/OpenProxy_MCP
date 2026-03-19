"""Step 3 테스트: KT&G 주주총회 소집공고 찾기 + 본문 일부 가져오기"""

import asyncio
import sys
import re
import io
import zipfile
import httpx

sys.stdout.reconfigure(encoding="utf-8")

from open_proxy_mcp.dart.client import DartClient


async def main():
    client = DartClient()

    # 1단계: 소집공고 검색 → KT&G 또는 케이티 필터
    print("=== 1단계: KT&G 소집공고 검색 ===\n")

    result = await client.search_filings(
        bgn_de="20260101",
        end_de="20260319",
        pblntf_ty="E",
    )

    filings = [
        item for item in result.get("list", [])
        if "소집" in item.get("report_nm", "")
        and ("KT" in item.get("corp_name", "").upper() or "케이티" in item.get("corp_name", ""))
    ]

    if not filings:
        filings = [item for item in result.get("list", []) if "소집" in item.get("report_nm", "")]
        print(f"KT&G 없음. 다른 소집공고로 테스트.\n")

    target = filings[0]
    print(f"  회사: {target['corp_name']}")
    print(f"  보고서명: {target['report_nm']}")
    print(f"  접수일: {target['rcept_dt']}")
    print(f"  접수번호: {target['rcept_no']}")
    print()

    # 2단계: document.xml → ZIP 다운로드 → XML 추출
    rcept_no = target["rcept_no"]
    print(f"=== 2단계: 공시 본문 가져오기 ===\n")

    async with httpx.AsyncClient(verify=False) as http:
        doc_url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={client.api_key}&rcept_no={rcept_no}"
        resp = await http.get(doc_url, timeout=30)

        # ZIP 해제
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        file_list = z.namelist()
        print(f"ZIP 내 파일 목록:")
        for f in file_list:
            print(f"  {f} ({z.getinfo(f).file_size:,} bytes)")
        print()

        # XML 파일 읽기
        xml_file = [f for f in file_list if f.endswith(".xml")][0]
        xml_content = z.read(xml_file)

        # 인코딩 처리
        for encoding in ["utf-8", "euc-kr", "cp949"]:
            try:
                text_html = xml_content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text_html = xml_content.decode("utf-8", errors="replace")

        # HTML/XML 태그 제거 → 순수 텍스트
        text = re.sub(r'<[^>]+>', ' ', text_html)
        text = re.sub(r'&[a-zA-Z]+;', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        print(f"본문 길이: {len(text):,}자\n")
        print("=== 본문 (첫 2000자) ===\n")
        print(text[:2000])


asyncio.run(main())
