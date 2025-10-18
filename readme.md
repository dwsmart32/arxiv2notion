# Arxiv2Notion

Arxiv2Notion is an automated tool that searches for newly published papers on [arXiv.org](https://arxiv.org), checks their relevance to your research, and logs them neatly into your Notion database.

---
## ⚙️ What should I modify to customize?
- Just modify `KEYWORDS`, `LOOKBACK_DAYS`, `MY_RESEARCH_AREA`, `prompt` and `ALLOWED_SUBJECTS` in `arxiv_to_notion.py` as you like.
- Just follow the [Setup Instructions](#setup-instructions), and you'll be able to use it with no trouble.
  
## 🔍 How It Works

- **Daily Search:**
  Runs every day at **9:00 AM KST** (customizable via the GitHub Actions workflow `.yml` file).

- **Keyword Matching:**
  Searches arXiv using a list of user-defined keywords in `arxiv_to_notion.py`. Keywords with hyphens (e.g., `few-shot`) are handled appropriately.

- **Smart Filtering:**
  Uses **Google Gemini models** to:
  - **Summarize paper**
  - **Determine relevance** to your research (`Related` / `Unrelated`)

- **Duplicate Handling:**
  Automatically filters out previously processed papers to avoid duplication.

---

## 🧠 Gemini Models

- The following Gemini models are used in sequence to support higher request rates (up to 45 RPM or 1550 RPD for free tier):
- Supporting model as of now: [`gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-2.5-flash-lite-preview-06-17`]
- It automatically changes a model based on the daily quota in order.

---

## ⚙️ Configuration

The script can be configured via `arxiv_to_notion.py` and GitHub Action secrets.

### 🔐 GitHub Secrets
- You should register these 3 parameters in `Settings -> Secrets and variables -> New repository secret`
- How to get your database ID? ([Eng](https://stackoverflow.com/questions/67728038/where-to-find-database-id-for-my-database-in-notion)) | ([Kor](https://nyukist.tistory.com/16))
- How to get notion token? ([Eng](https://developers.notion.com/docs/create-a-notion-integration)) | ([Kor](https://newdeal123.tistory.com/86))


| Name                  | Description                          |
|-----------------------|--------------------------------------|
| `NOTION_TOKEN`        | Your Notion integration token(==Notion API token)|
| `DATABASE_ID`         | Target Notion database ID            |
| `GOOGLE_API_KEY`      | Google Gemini API key (free or paid) |

### 🛠 Script Parameters
- You should change these parameters in `arxiv_to_notion.py` file.

| Parameter          | Description                                                       |
|--------------------|-------------------------------------------------------------------|
| `LOOKBACK_DAYS`    | How many days back from today to search on arXiv                  |
| `KEYWORDS`         | List of keywords to search for                                    |
| `MY_RESEARCH_AREA` | A short description of your research area (used to check relevance) |
| `ALLOWED_SUBJECTS` | As of now, we are using {"cs.CL"(NLP), "cs.AI"(ML), "cs.LG"(ML)} [refer to much more category](https://arxiv.org/category_taxonomy)|

---

## 🗃️ Notion Table Structure
- You should consider property type when you add column in your database table.

| Column Name                   | Property Type | Description                                      |
|------------------------------|----------------|--------------------------------------------------|
| Paper                        | title          | Title of the paper                              |
| Abstract                     | text           | Full abstract (via Gemini)                      |
| Relatedness                  | select         | Whether the paper is related to your research   |
| Date                         | date           | Publication date on arXiv                       |
| URL                          | url            | Direct link to the arXiv paper                  |
| Author                       | text           | Authors of the paper                            |
| Motivation                   | text           | Motivation of the paper                         |
| Differences from Prior Work  | text           | Differences from Prior Work                     |
| Contributions and Novelty    | text           | Contributions and Novelty                       |
| Proposed Method              | text           | Proposed Method of the paper                    |
| Results                      | text           | Results of the paper                            |


---

## 🛠 Setup Instructions

0. After issuing `Notion_TOKEN`, [link your api with your notion page that your database table exists](https://developers.notion.com/docs/create-a-notion-integration)(refer to   `Give your integration page permissions` Section in link)
1. **Fork/clone** this repository.
2. Set the following secrets in **GitHub → Settings → Secrets and variables → Actions**:
   - `NOTION_TOKEN`
   - `DATABASE_ID`
   - `GOOGLE_API_KEY`
3. Modify `KEYWORDS`, `LOOKBACK_DAYS`, and `MY_RESEARCH_AREA` in `arxiv_to_notion.py`.
4. Go to your notion page, then you should manually add each colum in your database table(in your page) with appropriate property type.(`Paper`, `Abstract`, `Relatedness`, ... `Results`)
5. That's it! The script will run daily via GitHub Actions.

---

## 📅 Scheduling 
- Default: **Every day at 09:00 AM KST**
- To change the schedule, edit the cron expression in `.github/workflows/main.yml`.

---
## 🔍 Author's Example
- [Author's Public Example](https://www.notion.so/SPL-paper-list-2248f62eeae280e191a4f831c41225f7?source=copy_link)
  
