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
import PyPDF2
import io
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("DATABASE_ID")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# ✅ [변경 1] 기본 키워드 목록을 간소화했습니다.
# 이 목록을 기반으로 모든 조합(하이픈, 대소문자)을 자동으로 생성합니다.
BASE_KEYWORDS = [
    "backchannel",
    "interruption",
    "SLM",
    "SLMs",
    "audio language model",
    "audio language models",
    "speech language model",
    "speech language models",
    "speech style",
    "spoken language model",
    "spoken language models",
    "speech to speech",
    "audio to speech",
    "Omni",
    "voice assistant",
    "Audio LLM",  # 대소문자 무관하게 입력해도 됩니다.
    "Audio LLMs",
    "prosody",
    "paralinguistics",
    "full duplex",
    "half duplex",
]

# ✅ [추가 1] 요청하신 키워드 확장 기능을 함수로 구현했습니다. (이전과 동일)
def expand_keywords(base_keywords):
    """
    기본 키워드 목록을 받아 다양한 변형(하이픈, 대소문자)을 생성합니다.
    - n어절 단어는 공백과 하이픈(-) 버전을 모두 생성합니다.
    - 각 버전에 대해 소문자, 대문자, 첫 글자 대문자 버전을 모두 생성합니다.
    - set을 사용하여 중복된 키워드는 자동으로 제거합니다.
    """
    expanded = set()
    for keyword in base_keywords:
        variants = set()
        if ' ' in keyword:
            variants.add(keyword.replace(' ', '-'))
        variants.add(keyword)

        for variant in variants:
            expanded.add(variant.lower())
            expanded.add(variant.upper())
            expanded.add(variant.title())
            
    return list(expanded)

# ✅ [추가 2] 위에서 만든 함수를 호출하여 최종 검색 키워드 목록을 생성합니다.
KEYWORDS = expand_keywords(BASE_KEYWORDS)

ALLOWED_SUBJECTS = {"cs.CL", "cs.AI", "cs.LG", "cs.SD"}
MY_RESEARCH_AREA = "My research focuses on developing virtual agents that understand user situations by jointly reasoning over user speech and ambient sounds as multimodal input, with a particular emphasis on generating speech with diverse styles using audio language models."
LOOKBACK_DAYS = 60

# Basic check to ensure secrets were loaded
if not all([NOTION_TOKEN, DATABASE_ID, GOOGLE_API_KEY]):
    raise ValueError("❌ One or more secret environment variables are not set. Please check your GitHub repository secrets.")

MODEL_LIST = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite-preview-06-17"]

current_model_index = 0 # 사용할 모델을 가리키는 인덱스

# ✅ 날짜 계산도 config 기반으로
today = datetime.today()
yesterday = today - timedelta(days=LOOKBACK_DAYS)

# ✅ Gemini client 설정
client = genai.Client(api_key=GOOGLE_API_KEY)

def fetch_existing_papers():
    """Notion 데이터베이스에서 기존 논문 URL을 가져옵니다."""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    existing_papers = set()
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
                    paper_url = page["properties"]["URL"]["url"]  # 논문의 URL을 가져옵니다.
                    existing_papers.add(paper_url)
                except (KeyError, IndexError):
                    continue
            has_more = results.get("has_more", False)
            next_cursor = results.get("next_cursor")
        except requests.exceptions.RequestException as e:
            print(f"❌ Notion 제목 조회 중 오류 발생: {e}")
            break
    return existing_papers

def fetch_arxiv_papers():
    """키워드를 기반으로 arXiv에서 논문을 검색하고 날짜와 카테고리로 필터링합니다."""
    base_url = "http://export.arxiv.org/api/query?"
    unique_papers = {}
    print("⬇️  키워드 기반 arXiv 논문 다운로드 시작...")
    for keyword in set(KEYWORDS):
        print(f"🔎 키워드 검색 중: \"{keyword}\"")
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
            paper_abs_url = entry.id.text.strip()
            pdf_link_tag = entry.find('link', attrs={'title': 'pdf'})
            if pdf_link_tag and pdf_link_tag.get('href'):
                paper_pdf_url = pdf_link_tag['href']
            else:
                abs_https = paper_abs_url.replace('http://', 'https://')
                paper_pdf_url = abs_https.replace('/abs/', '/pdf/')
                if not paper_pdf_url.endswith('.pdf'):
                    paper_pdf_url += '.pdf'
            
            if paper_abs_url not in unique_papers:
                clean_title = ' '.join(entry.title.text.strip().split())
                clean_abstract = ' '.join(entry.summary.text.strip().split())
                unique_papers[paper_abs_url] = {
                    'title': clean_title,
                    'link': paper_abs_url.replace('http://', 'https://'),
                    'pdf_link': paper_pdf_url,
                    'updated_str': entry.updated.text,
                    'abstract': clean_abstract,
                    'author': entry.author.find('name').text.strip() if entry.author else 'arXiv',
                    'categories': [cat['term'] for cat in entry.find_all('category')]
                }
        time.sleep(1)
    print(f"👍 총 {len(unique_papers)}개의 고유 논문 발견. 필터링 시작...")
    filtered_papers = []
    for paper in unique_papers.values():
        updated_date = datetime.strptime(paper['updated_str'], "%Y-%m-%dT%H:%M:%SZ").date()
        if not (yesterday.date() <= updated_date <= today.date()):
            continue
        if not any(subject in paper['categories'] for subject in ALLOWED_SUBJECTS):
            continue
        filtered_papers.append(paper)
    return filtered_papers

def check_pdf_for_pages(pdf_data):
    try:
        reader = PyPDF2.PdfFileReader(io.BytesIO(pdf_data))
        num_pages = reader.getNumPages()
        return num_pages > 0
    except PyPDF2.utils.PdfReadError:
        return False
        
def analyze_paper_with_gemini(paper):
    """
    Gemini를 사용하여 PDF 논문을 분석하고, 요약을 5개 항목으로 파싱하여 반환합니다.
    """
    global current_model_index
    try:
        print(f"  - PDF 다운로드 중: {paper['pdf_link']}")
        headers = {"User-Agent": "paper-bot/1.0 (+contact@example.com)"}
        doc_response = httpx.get(
            paper['pdf_link'],
            timeout=30,
            headers=headers,
            follow_redirects=True,
        )
        doc_response.raise_for_status()
        doc_data = doc_response.content
        print("  - PDF 다운로드 완료.")
        
        if not check_pdf_for_pages(doc_data):
            print("  ❌ PDF 파일에 페이지가 없습니다. 이 논문은 분석하지 않습니다.")
            return None, None
            
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        print(f"  ❌ PDF 다운로드/처리 실패: {e}")
        return None, None

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
            response = client.models.generate_content(
                model=model_to_use,
                contents=[
                    types.Part.from_bytes(data=doc_data, mime_type='application/pdf'),
                    prompt
                ],
            )
            if response.text and '|||' in response.text:
                summary_part, answer_part = [p.strip() for p in response.text.strip().split('|||', 1)]
                tags = ["MOTIVATION", "DIFFERENCES", "CONTRIBUTIONS", "METHOD", "RESULTS"]
                parsed_summary = {}
                for i in range(len(tags)):
                    current_tag = tags[i]
                    next_tag = tags[i+1] if i + 1 < len(tags) else None
                    if next_tag:
                        pattern = f"\[{current_tag}\](.*?)(?=\[{next_tag}\])"
                    else:
                        pattern = f"\[{current_tag}\](.*)"
                    match = re.search(pattern, summary_part, re.DOTALL | re.IGNORECASE)
                    if match:
                        content = match.group(1).strip()
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
        "Abstract": {"rich_text": [{"text": {"content": paper.get('abstract', '')}}]},
        "Author": {"rich_text": [{"text": {"content": paper.get('author', 'arXiv')}}]},
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

def main():
    """메인 스크립트 실행 함수"""
    print("🚀 논문 자동화 스크립트를 시작합니다.")
    print("\n[1/4] 📚 Notion DB에서 기존 논문 목록 가져오는 중...")
    existing_papers = fetch_existing_papers()  # 변경된 함수 사용
    print(f"총 {len(existing_papers)}개의 논문이 Notion에 존재합니다.")
    print("\n[2/4] 🔍 arXiv에서 신규 논문 검색 및 필터링 중...")
    arxiv_papers = fetch_arxiv_papers()
    print(f"👍 날짜/주제 필터 통과한 논문 수: {len(arxiv_papers)}")
    final_papers_to_add = []
    if arxiv_papers:
        print("\n[3/4] 🤖 Gemini 관련도 분석 및 항목별 요약 시작...")
        new_papers = [p for p in arxiv_papers if p['link'] not in existing_papers]  # URL을 기준으로 중복 제거
        print(f"중복을 제외한 신규 논문 {len(new_papers)}개를 분석합니다.")
        for i, paper in enumerate(new_papers):
            print(f"({i+1}/{len(new_papers)}) 🔬 Gemini 분석 중: {paper['title'][:60]}...")
            related_status, summary_parts = analyze_paper_with_gemini(paper)
            if related_status and summary_parts:
                final_papers_to_add.append((paper, related_status, summary_parts))
                print(f"👍 Gemini 분석 완료! (상태: {related_status})")
            else:
                print(f"👎 Gemini 분석 실패. 이 논문은 등록되지 않습니다.")
            time.sleep(1)
    print(f"\n[4/4] 📝 Notion DB에 최종 논문 등록 시작...")
    if not final_papers_to_add:
        print("✨ 새로 추가할 논문이 없습니다.")
    else:
        print(f"총 {len(final_papers_to_add)}개의 새로운 논문을 Notion에 추가합니다.")
        for paper, status, parts in final_papers_to_add:
            add_to_notion(paper, status, parts)
            time.sleep(0.5)
    print("\n🎉 모든 작업이 완료되었습니다!")

if __name__ == "__main__":
    main()
