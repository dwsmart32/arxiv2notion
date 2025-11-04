import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from google import genai
import time
from google.genai import types
import httpx
import re

# --- 설정 (Secrets) ---
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("DATABASE_ID_MP")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
S2_API_KEY = os.environ.get("SEMANTICSCHOLAR_API_KEY") # ✅ [S2 추가]

# --- 설정 (키워드 및 필터) ---
BASE_KEYWORDS = [
    "Multi Party",
    "Multi Party Dialogues",
    "Multi speaker",
    "Multi speakers"
]

# ✅ [S2 통합] arXiv와 S2의 카테고리 이름이 다르므로 분리합니다.
ARXIV_ALLOWED_SUBJECTS = {"cs.CL", "cs.AI", "cs.LG", "cs.SD"}
S2_ALLOWED_SUBJECTS = {"Computer Science", "Linguistics", "Engineering"} # ✅ [S2 추가]

MY_RESEARCH_AREA = "My research focuses on developing full duplex spoken language model that understands the multi-party conversation and situations"
LOOKBACK_DAYS = 360

# --- 기본 체크 ---
missing = [name for name, val in {
    "NOTION_TOKEN": NOTION_TOKEN,
    "DATABASE_ID_MP": DATABASE_ID,
    "GOOGLE_API_KEY": GOOGLE_API_KEY,
    "SEMANTICSCHOLAR_API_KEY": S2_API_KEY
}.items() if not val]

if missing:
    raise ValueError(f"❌ 다음 환경 변수가 설정되지 않았습니다: {', '.join(missing)}")
    
MODEL_LIST = ["gemini-1.5-pro-latest", "gemini-1.5-flash-latest", "gemini-pro"] # ✅ 모델 리스트 최신화
current_model_index = 0

today = datetime.today()
lookback_date_obj = today - timedelta(days=LOOKBACK_DAYS) # ✅ [S2 통합] 날짜 객체로 저장

# --- Gemini 클라이언트 설정 ---
client = genai.Client(api_key=GOOGLE_API_KEY)


# --- 키워드 확장 함수 ---
def expand_keywords(base_keywords):
    """
    기본 키워드 목록을 받아 다양한 변형(하이픈, 대소문자)을 생성합니다.
    """
    expanded = set()
    for keyword in base_keywords:
        variants = {keyword}
        if ' ' in keyword:
            variants.add(keyword.replace(' ', '-'))
        if '-' in keyword:
            variants.add(keyword.replace('-', ' '))

        for variant in variants:
            expanded.add(variant.lower())
            expanded.add(variant.upper())
            expanded.add(variant.title())
            
    return list(expanded)

# ✅ [S2 통합] 최종 검색 키워드 목록
KEYWORDS = expand_keywords(BASE_KEYWORDS)


# --- Notion DB 함수 ---
def fetch_existing_titles():
    """Notion 데이터베이스에서 기존 논문 제목들을 가져옵니다."""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    titles = set()
    has_more = True
    next_cursor = None
    while has_more:
        data = {"start_cursor": next_cursor} if next_cursor else {}
        try:
            res = requests.post(url, headers=headers, json=data, timeout=10)
            res.raise_for_status()
            results = res.json()
            for page in results["results"]:
                try:
                    title = ' '.join(page["properties"]["Paper"]["title"][0]["text"]["content"].split())
                    titles.add(title)
                except (KeyError, IndexError):
                    continue
            has_more = results.get("has_more", False)
            next_cursor = results.get("next_cursor")
        except requests.exceptions.RequestException as e:
            print(f"❌ Notion 제목 조회 중 오류 발생: {e}")
            break
    return titles

# --- ArXiv 논문 수집 함수 ---
def fetch_arxiv_papers(lookback_date):
    """키워드를 기반으로 arXiv에서 논문을 검색하고 날짜와 카테고리로 필터링합니다."""
    base_url = "http://export.arxiv.org/api/query?"
    unique_papers = {}
    print("⬇️  [ArXiv] 키워드 기반 논문 다운로드 시작...")
    print(f"💡 총 {len(KEYWORDS)}개의 확장된 키워드로 검색을 시작합니다: {KEYWORDS}")
    
    today_date = datetime.today().date()

    for keyword in set(KEYWORDS):
        print(f"🔎 [ArXiv] 키워드 검색 중: \"{keyword}\"")
        search_query = f'ti:"{keyword}" OR abs:"{keyword}"'
        params = f"search_query={search_query}&sortBy=submittedDate&sortOrder=descending&max_results=50"
        try:
            response = requests.get(base_url + params, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"❌ \"{keyword}\" 검색 중 arXiv API 오류: {e}")
            continue
        
        soup = BeautifulSoup(response.content, 'xml')
        entries = soup.find_all('entry')
        
        for entry in entries:
            # --- 날짜 필터링 (ArXiv) ---
            updated_str = entry.updated.text
            updated_date = datetime.strptime(updated_str, "%Y-%m-%dT%H:%M:%SZ").date()
            if not (lookback_date <= updated_date <= today_date):
                continue

            # --- 카테고리 필터링 (ArXiv) ---
            categories = [cat['term'] for cat in entry.find_all('category')]
            if not any(subject in categories for subject in ARXIV_ALLOWED_SUBJECTS):
                continue

            paper_abs_url = entry.id.text.strip()
            if paper_abs_url not in unique_papers:
                pdf_link_tag = entry.find('link', attrs={'title': 'pdf'})
                if pdf_link_tag and pdf_link_tag.get('href'):
                    paper_pdf_url = pdf_link_tag['href']
                else:
                    abs_https = paper_abs_url.replace('http://', 'https://')
                    paper_pdf_url = abs_https.replace('/abs/', '/pdf/')
                    if not paper_pdf_url.endswith('.pdf'):
                        paper_pdf_url += '.pdf'
                
                unique_papers[paper_abs_url] = {
                    'title': ' '.join(entry.title.text.strip().split()),
                    'link': paper_abs_url.replace('http://', 'https://'),
                    'pdf_link': paper_pdf_url,
                    'updated_str': updated_str, # ArXiv는 이미 ISO 형식이므로 그대로 사용
                    'abstract': ' '.join(entry.summary.text.strip().split()),
                    'author': entry.author.find('name').text.strip() if entry.author else 'arXiv',
                    'categories': categories
                }
        time.sleep(1)
        
    print(f"👍 [ArXiv] 총 {len(unique_papers)}개의 고유 논문 발견.")
    return list(unique_papers.values())


# --- ✅ [S2 추가] Semantic Scholar 논문 수집 함수 ---
def fetch_semantic_scholar_papers(keywords, lookback_date):
    """
    키워드를 기반으로 Semantic Scholar에서 논문을 검색하고
    날짜와 카테고리로 필터링하여 '표준 형식'으로 반환합니다.
    """
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    
    s2_fields = [
        "paperId", "url", "title", "abstract", "authors",
        "publicationDate", "openAccessPdf", "fieldsOfStudy"
    ]
    
    headers = {'X-API-KEY': S2_API_KEY}
    unique_papers = {}
    today_date = datetime.today().date()

    print(f"⬇️  [S2] Semantic Scholar 논문 검색 시작 (최근 {LOOKBACK_DAYS}일)...")

    for keyword in set(keywords):
        print(f"🔎 [S2] 키워드 검색 중: \"{keyword}\"")
        
        params = {
            'query': keyword,
            'fields': ','.join(s2_fields),
            'sort': 'publicationDate:desc',
            'limit': 50
        }
        
        try:
            response = requests.get(base_url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            results = response.json()

            for paper_data in results.get('data', []):
                paper_id = paper_data.get('paperId')
                if not paper_id or paper_id in unique_papers:
                    continue

                # --- 1. 날짜 필터링 (S2) ---
                pub_date_str = paper_data.get('publicationDate')
                if not pub_date_str:
                    continue
                
                try:
                    pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue 

                if not (lookback_date <= pub_date <= today_date):
                    continue

                # --- 2. 카테고리 필터링 (S2) ---
                categories = paper_data.get('fieldsOfStudy') or []
                if not categories or not any(subject in S2_ALLOWED_SUBJECTS for subject in categories):
                    continue
                
                # --- 3. 표준 형식으로 파싱 (S2) ---
                authors_list = paper_data.get('authors', [])
                author_str = authors_list[0].get('name', 'S2') if authors_list else 'S2'
                
                oa_pdf = paper_data.get('openAccessPdf')
                pdf_link = oa_pdf.get('url') if (oa_pdf and oa_pdf.get('url')) else paper_data.get('url')

                # Notion 저장을 위해 ISO T Z 형식으로 변환
                updated_str_iso = f"{pub_date_str}T00:00:00Z"

                # ✅ [수정] .get()으로 가져온 값이 None일 경우(JSON: null) 'or'로 기본값 설정
                title_raw = paper_data.get('title')
                abstract_raw = paper_data.get('abstract')

                unique_papers[paper_id] = {
                    'title': ' '.join((title_raw or 'No Title').split()),
                    'link': paper_data.get('url'),
                    'pdf_link': pdf_link,
                    'updated_str': updated_str_iso,
                    'abstract': ' '.join((abstract_raw or 'N/A').split()),
                    'author': author_str,
                    'categories': categories
                }

        except requests.exceptions.RequestException as e:
            print(f"❌ \"{keyword}\" 검색 중 S2 API 오류: {e}")
            continue
        
        time.sleep(1) # API 속도 제한 준수

    print(f"👍 [S2] 총 {len(unique_papers)}개의 고유 논문 발견.")
    return list(unique_papers.values())

# --- Gemini 분석 함수 ---
def analyze_paper_with_gemini(paper):
    """
    Gemini를 사용하여 PDF 논문을 분석하고, 요약을 5개 항목으로 파싱하여 반환합니다.
    """
    global current_model_index

    # --- PDF 다운로드 ---
    try:
        print(f"  - PDF 다운로드 중: {paper['pdf_link']}")
        headers = {"User-Agent": "paper-bot/1.0 (+github.com/dongwook-lee)"} # User-Agent 명시
        
        # httpx로 리다이렉트 자동 처리
        with httpx.Client(follow_redirects=True, timeout=30) as http_client:
             doc_response = http_client.get(paper['pdf_link'], headers=headers)
             doc_response.raise_for_status()
             doc_data = doc_response.content
        print("  - PDF 다운로드 완료.")
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        print(f"  ❌ PDF 다운로드/처리 실패: {e}")
        return None, None

    # --- Gemini 프롬프트 (항목별 태그 추가) ---
    prompt = f"""
    You are an AI assistant helping a researcher. Your task is to analyze the attached PDF paper and provide two outputs: an English summary divided into five specific sections, and an assessment of its relevance.

    **My Research Area:**
    "{MY_RESEARCH_AREA}"

    **Instructions:**

    1.  **Paper Summary (English):** Please summarize the paper, strictly following the five-part structure below. Use the exact tags `[MOTIVATION]`, `[DIFFERENCES]`, `[CONTRIBUTIONS]`, `[METHOD]`, `[RESULTS]` to label each section. Each section should be a concise paragraph.
        * `[MOTIVATION]`: What problem does this research aim to solve, and why is it important?
        * `[DIFFERENCES]`: How is this work different from or improving upon previous approaches?
        * `[CONTRIBUTIONS]`: What are the main contributions and novel aspects of this paper?
        * `[METHOD]`: What method or approach do the authors propose?
        * `[RESULTS]`: What are the key results that demonstrate the effectiveness of the proposed method?

    2.  **Relevance Assessment:** Please determine if the paper’s contributions are directly relevant to my research area.

    3.  **Output Format:** You **MUST** follow the exact format below, using "|||" as a delimiter. Do not include any additional commentary or greetings.

    **Output Format:**
    [MOTIVATION]
    ... summary ...
    [DIFFERENCES]
    ... summary ...
    [CONTRIBUTIONS]
    ... summary ...
    [METHOD]
    ... summary ...
    [RESULTS]
    ... summary ...
    |||[Yes. or No.]
    """

    while current_model_index < len(MODEL_LIST):
        model_to_use = MODEL_LIST[current_model_index]
        print(f"  - Gemini 분석 시도 (모델: {model_to_use})")
        
        try:
            # ✅ [S2 통합] 최신 Gemini API 호출 방식 (genai.Client)
            response = client.models.generate_content(
                model=model_to_use,
                contents=[
                    types.Part.from_bytes(data=doc_data, mime_type='application/pdf'),
                    prompt
                ],
            )

            if response.text and '|||' in response.text:
                summary_part, answer_part = [p.strip() for p in response.text.strip().split('|||', 1)]
                
                # --- 정규표현식을 이용한 파싱 ---
                tags = ["MOTIVATION", "DIFFERENCES", "CONTRIBUTIONS", "METHOD", "RESULTS"]
                parsed_summary = {}
                for i in range(len(tags)):
                    current_tag = tags[i]
                    next_tag = tags[i+1] if i + 1 < len(tags) else None
                    
                    pattern = f"\[{current_tag}\](.*?)"
                    if next_tag:
                        pattern = f"\[{current_tag}\](.*?)(?=\[{next_tag}\])"
                    else:
                        pattern = f"\[{current_tag}\](.*)"
                    
                    match = re.search(pattern, summary_part, re.DOTALL | re.IGNORECASE)
                    
                    if match:
                        content = match.group(1).strip()
                        # Notion의 텍스트 필드 최대 길이는 2000자입니다.
                        parsed_summary[current_tag] = content[:1990] + '...' if len(content) > 2000 else content
                    else:
                        parsed_summary[current_tag] = "N/A"

                if all(tag in parsed_summary for tag in tags):
                    relevance = "Related" if "yes" in answer_part.lower() else "Unrelated"
                    return relevance, parsed_summary
            
            print(f"  ⚠️ Gemini가 예상치 못한 형식으로 답변: {response.text[:200]}...")
            return None, None

        except Exception as e:
            if "overload" in str(e).lower():
                print(f"  ⏳ 모델 '{model_to_use}' 과부하. 30초 후 재시도합니다.")
                time.sleep(30)
                continue
            else:
                if "resource_exhausted" in str(e).lower() or "quota" in str(e).lower():
                    print(f"  ⚠️ 모델 '{model_to_use}'의 API 쿼터 소진. 다음 모델로 전환합니다.")
                    current_model_index += 1
                    time.sleep(2)
                else:
                    print(f"  ❌ Gemini API 호출 중 예상치 못한 오류 발생: {e}")
                    return None, None

    print("  ❌ 사용 가능한 모든 Gemini 모델의 쿼터를 소진했습니다.")
    return None, None

# --- Notion 추가 함수 ---
def add_to_notion(paper, related_status, summary_parts):
    """논문 정보, 관련도, 분할된 요약을 Notion에 추가합니다."""
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    updated_str = paper['updated_str'].split('T')[0]

    properties = {
        "Paper": {"title": [{"text": {"content": paper['title']}}]},
        "Abstract": {"rich_text": [{"text": {"content": paper.get('abstract', 'N/A')[:1999]}}]}, # 원본 초록 (길이 제한)
        "Author": {"rich_text": [{"text": {"content": paper.get('author', 'N/A')}}]},
        "Relatedness": {"select": {"name": related_status}},
        "URL": {"url": paper['link']},
        "Date": {"date": {"start": updated_str}},
        "Motivation": {"rich_text": [{"text": {"content": summary_parts.get('MOTIVATION', 'N/A')}}]},
        "Differences from Prior Work": {"rich_text": [{"text": {"content": summary_parts.get('DIFFERENCES', 'N/A')}}]},
        "Contributions and Novelty": {"rich_text": [{"text": {"content": summary_parts.get('CONTRIBUTIONS', 'N/A')}}]},
        "Proposed Method": {"rich_text": [{"text": {"content": summary_parts.get('METHOD', 'N/A')}}]},
        "Results": {"rich_text": [{"text": {"content": summary_parts.get('RESULTS', 'N/A')}}]}
    }

    data = {"parent": {"database_id": DATABASE_ID}, "properties": properties}

    try:
        res = requests.post(url, headers=headers, json=data, timeout=15)
        if res.status_code == 200:
            print(f"✅ Notion 등록 성공: {paper['title'][:60]}... (상태: {related_status})")
        else:
            print(f"❌ Notion 등록 실패: {paper['title'][:60]}...")
            print(f"📄 Notion 응답: {res.status_code}")
            print(res.text)
    except requests.exceptions.RequestException as e:
        print(f"❌ Notion API 요청 실패: {paper['title'][:60]}... | {e}")


# --- 🚀 메인 실행 함수 ---
def main():
    """메인 스크립트 실행 함수"""
    print("🚀 논문 자동화 스크립트를 시작합니다. (ArXiv + Semantic Scholar)")
    
    # --- ✅ [S2 통합] 날짜 객체를 함수에 전달하도록 수정 ---
    lookback_date = lookback_date_obj.date()

    print("\n[1/5] 📚 Notion DB에서 기존 논문 목록 가져오는 중...")
    existing_titles_lower = {title.lower() for title in fetch_existing_titles()}
    print(f"총 {len(existing_titles_lower)}개의 논문이 Notion에 존재합니다.")

    print("\n[2/5] 🔍 논문 수집 중...")
    # --- ✅ [S2 통합] 두 소스에서 모두 논문을 가져옵니다. ---
    arxiv_papers = fetch_arxiv_papers(lookback_date)
    s2_papers = fetch_semantic_scholar_papers(KEYWORDS, lookback_date)
    
    all_papers_raw = arxiv_papers + s2_papers
    print(f"--- \n➡️  총 {len(all_papers_raw)}개 논문 발견 (ArXiv: {len(arxiv_papers)}, S2: {len(s2_papers)})")

    # --- ✅ [S2 통합] (중요) S2와 ArXiv의 중복을 제목 기준으로 제거합니다. ---
    print("\n[3/5] 🔄 (ArXiv + S2) 통합 리스트 중복 제거 중...")
    unique_papers_dict = {}
    for paper in all_papers_raw:
        title_lower = paper['title'].lower()
        if title_lower not in unique_papers_dict:
            unique_papers_dict[title_lower] = paper
    
    all_papers_filtered = list(unique_papers_dict.values())
    print(f"👍 중복 제거 후 총 {len(all_papers_filtered)}개의 고유 논문 확보.")

    analyzed_papers = []
    if all_papers_filtered:
        print("\n[4/5] 🤖 Gemini 관련도 분석 및 항목별 요약 시작...")
        
        # --- ✅ [S2 통합] Notion DB와 중복 체크 ---
        new_papers_to_analyze = [p for p in all_papers_filtered if p['title'].lower() not in existing_titles_lower]
        print(f"Notion DB 중복 제외 후, {len(new_papers_to_analyze)}개의 신규 논문을 분석합니다.")

        for i, paper in enumerate(new_papers_to_analyze):
            print(f"--- ({i+1}/{len(new_papers_to_analyze)}) 🔬 Gemini 분석 중: {paper['title'][:60]}...")
            
            related_status, summary_parts = analyze_paper_with_gemini(paper)

            if related_status and summary_parts:
                analyzed_papers.append((paper, related_status, summary_parts))
                print(f"👍 Gemini 분석 완료! (상태: {related_status})")
            else:
                print(f"👎 Gemini 분석 실패. 이 논문은 등록되지 않습니다.")
            time.sleep(1) # Gemini API 속도 제한

    print(f"\n[5/5] 📝 Notion DB에 최종 논문 등록 시작...")
    if not analyzed_papers:
        print("✨ 새로 추가할 논문이 없습니다.")
    else:
        # ✅ [S2 통합] Race Condition 방지를 위해 최종 목록을 다시 가져옵니다.
        print("🔄 최종 중복 체크를 위해 Notion DB 목록을 다시 가져옵니다...")
        final_existing_titles_lower = {title.lower() for title in fetch_existing_titles()}
        
        final_papers_to_add = [
            (paper, status, parts)
            for paper, status, parts in analyzed_papers
            if paper['title'].lower() not in final_existing_titles_lower
        ]

        if not final_papers_to_add:
            print("✨ 최종 중복 체크 결과, 새로 추가할 논문이 없습니다.")
        else:
            print(f"총 {len(final_papers_to_add)}개의 새로운 논문을 Notion에 추가합니다.")
            for paper, status, parts in final_papers_to_add:
                add_to_notion(paper, status, parts)
                time.sleep(0.5) # Notion API 속도 제한

    print("\n🎉 모든 작업이 완료되었습니다!")

if __name__ == "__main__":
    main()
