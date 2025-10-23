# Arxiv2Notion

Arxiv2Notion enables searching for newly published papers based on your preferences using [arXiv.org API](https://arxiv.org), checks recent, relevant papers to your research, and easily follow up!

---

## 🔍 How It Works

- **Daily Search:**
  It searches for papers for you every day at **9:00 AM KST**.(customizable via the GitHub Actions workflow `.yml` file).

- **Keyword Matching:**
  It searches arXiv using a list of user-defined keywords in `arxiv_to_notion.py`.

- **Smart Filtering:**
  Uses **Google Gemini models** to:
  - **Summarize paper**
  - **Determine relevance** to your research (`Related` / `Unrelated`)

- **Duplicate Handling:**
  Automatically filters out previously processed papers to avoid duplication based on the Title.

---
## ⚙️ How to Customize Yours?
- Just modify `BASE_KEYWORDS`, `LOOKBACK_DAYS`, `MY_RESEARCH_AREA`, `prompt` and `ALLOWED_SUBJECTS` in `arxiv_to_notion.py` as you like.
- Just follow the [Setup Instruction](#setup-instruction), and you'll be able to use it with no trouble.

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
| `BASE_KEYWORDS`    | List of keywords to search for                                    |
| `MY_RESEARCH_AREA` | A short description of your research area (used to check relevance) |
| `ALLOWED_SUBJECTS` | As of now, we are using {"cs.CL"(NLP), "cs.AI"(ML), "cs.LG"(ML)} [refer to much more category](https://arxiv.org/category_taxonomy)|

---

## 🗃️ Notion Table Structure
- You should match property `Column Name` and `Property Type` below and the those of each colum in your notion table when you add column in your database table. You don't need to set the property type of the first column. It will be automatically set, once you create `database table`.

| Column Name                   | Property Type |
|------------------------------|----------------|
| Paper                        | no need to set |
| Abstract                     | text           | 
| Relatedness                  | select         | 
| Date                         | date           | 
| URL                          | url            | 
| Author                       | text           | 
| Motivation                   | text           | 
| Differences from Prior Work  | text           | 
| Contributions and Novelty    | text           | 
| Proposed Method              | text           | 
| Results                      | text           |


---

## 🛠 Setup Instruction

0. After issuing `Notion_TOKEN`, [link your api with your notion page that your database table exists](https://developers.notion.com/docs/create-a-notion-integration)(refer to   `Give your integration page permissions` Section in link)
1. **Fork/clone** this repository.
2. Set the following secrets in **GitHub → Settings → Secrets and variables → Actions**:
   - `NOTION_TOKEN`
   - `DATABASE_ID`
   - `GOOGLE_API_KEY`
3. Modify `BASE_KEYWORDS`, `LOOKBACK_DAYS`, and `MY_RESEARCH_AREA` in `arxiv_to_notion.py`.
4. Go to your notion page, then you should manually add each colum in your database table(in your page) with appropriate property type.(`Paper`, `Abstract`, `Relatedness`, ... `Results`)
5. That's it! The script will run daily via GitHub Actions.

---

## 📅 Scheduling 
- Default: **Every day at 09:00 AM KST**
- To change the schedule, edit the cron expression in `.github/workflows/main.yml`.

---
## 🔍 What if I want to operate additional database table in parallel?
1. Add `notion_arxiv2.py` file as you did(`notion_arxiv_fd.py` in the case of this repo).
2. Make new database table in your new notion page.
3. Change `DATABASE_ID` of `notion_arxiv2.py` into `DATABASE_ID_2` (or whatever you like. This repo adds `fd` for a second database instead of `_2`.)
4. Set the `DATABASE_ID_2` secrets in **GitHub → Settings → Secrets and variables → Actions** as you did.
5. Add several lines running `notion_arxiv2.py` in `.github/workflows/main.yml` file same as `notion_arxiv.py` part.
6. Change other variables according to your preference.

---
## 🔍 Result Visualization
- [Notion Database Example](https://www.notion.so/SPL-paper-list-2248f62eeae280e191a4f831c41225f7?source=copy_link)
  
