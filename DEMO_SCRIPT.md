# Database Discovery POC — Live Demo Script

**One story, screen by screen. Fill "Your values" once, then follow the flow — no gaps.**

---

## Table of contents

| Chapter | Title |
|---------|--------|
| **1** | [Your values & quick reference](#chapter-1-your-values--quick-reference) |
| **2** | [On the day — Before you start](#chapter-2-on-the-day--before-you-start) |
| **3** | [The story — Screen by screen](#chapter-3-the-story--screen-by-screen) |
| **4** | [Flow in one line](#chapter-4-flow-in-one-line) |
| **5** | [If they ask (short answers)](#chapter-5-if-they-ask-short-answers) |
| **6** | [Checklists & readiness](#chapter-6-checklists--readiness) |

---

# Chapter 1 — Your values & quick reference

## 1.1 Your values (fill before the demo)

| What | Your value |
|------|------------|
| **API base URL** | `https://_________.execute-api.ap-south-1.amazonaws.com/prod` |
| **Account ID** | e.g. `587010590580` |

---

## 1.2 Quick note — What to show next & where to access (if you forget)

| # | What to show | Where to access |
|---|----------------|-----------------|
| 1 | **Table with discovery results** | **AWS Console** → search **DynamoDB** → left: **Tables** → click **db-discovery-results** → **Explore table items** → **Scan** |
| 2 | **Discovery Lambda (code + Test)** | **AWS Console** → search **Lambda** → **Functions** → click **db-discovery** → **Code** tab, then **Test** tab → run Test |
| 3 | **What runs on the server (document)** | **AWS Console** → search **Systems Manager** → left: **Documents** → click **DBDiscovery** → **Content** tab |
| 4 | **The script in storage** | **AWS Console** → search **S3** → **Buckets** → click your bucket (e.g. my-db-discovery-bucket) → open folder **ssm** → file **discovery_python.py** |
| 5 | **The server (EC2 / Fleet Manager)** | **EC2:** search **EC2** → **Instances** — or **Systems Manager** → left: **Fleet Manager** → see instance **Online** |
| 6 | **API Lambda (code)** | **AWS Console** → search **Lambda** → **Functions** → click **db-discovery-api** → **Code** tab |
| 7 | **API routes (URL)** | **AWS Console** → search **API Gateway** → **APIs** → click your API → left: **Resources** (see /health, /accounts/{accountId}/instances) — or **Stages** → **prod** → copy **Invoke URL** |
| 8 | **Browser — same data as API** | Open browser → **URL 1:** `YOUR_API_URL/health` → **URL 2:** `YOUR_API_URL/accounts/YOUR_ACCOUNT_ID/instances` (use your values from §1.1) |

**Tip:** Keep this table visible (second screen or printed) so you always know “next = #X” and “where = that row.”

---

# Chapter 2 — On the day — Before you start

1. **EC2** → Start your instance (if stopped).  
2. **Fleet Manager** → Wait until the instance shows **Online** (1–2 min).  
3. **Optional:** Run the discovery Lambda once so the table has data.  
4. Open tabs in this order: **DynamoDB** → **Lambda db-discovery** → **SSM Documents** → **S3** → **Lambda db-discovery-api** → **API Gateway** → **Browser**. Then tell the story in Chapter 3 as you click through.

---

# Chapter 3 — The story — Screen by screen

## Opening (one sentence)

*"I'll show you each piece: where the data lives, what fills it, what runs on the server, and how we expose it as an API. Everything connects in one flow."*

---

### 3.1 DynamoDB — “Where the data lives”

**Show:** Tables → *db-discovery-results* → Explore table items → Scan.

**Say:**  
*"This is **where the results live**. Each row is one finding: which account, which server, and which database — MySQL, Postgres, MongoDB — or 'none' if there's no DB on that server. We didn't type this in; something **writes** it. I'll show you what."*

**What we did here:** Created one table. Key = account + instance+db so we can query by account.  
**What writes here:** The discovery Lambda (next screen) after it runs a script on the servers.  
**Why:** One place for all discovery results so the API can read from it later.

---

### 3.2 Lambda — db-discovery — “What fills the table”

**Show:** Lambda → *db-discovery* → Code tab (scroll to show it's Python), then Test tab → run Test.

**Say:**  
*"This is the **discovery** Lambda. The **code** does four things: it gets the list of servers that work with AWS (no SSH needed), tells AWS to **run a small script** on each of them, **reads the script's output**, and **writes rows** into the table you just saw. So when I click **Test**, it goes to each server, runs the script, and fills the table. No login to any server."*

**What we did here:** Wrote Python that talks to AWS (list servers, run command, get output) and DynamoDB (write rows).  
**What the code does:** For each account in our list: assume that account's role → list managed servers → send “run this document” → wait → read what the script printed → parse it → write to the table.  
**Why:** So we have one button (or schedule) that refreshes the table from all servers without SSH.

---

### 3.3 Systems Manager — Documents — “What runs on the server”

**Show:** Systems Manager → Documents → *DBDiscovery* → Content tab (show the few lines: download from S3, run Python).

**Say:**  
*"This is **what actually runs on the server**. It's just two steps: **download the script** from storage and **run it** with Python. We don't install anything on the server; the script is fetched each time. So the server only runs this short recipe — download and run — and the **script** does the real work. I'll show you the script next."*

**What we did here:** Created one “document” that AWS runs on the server. It takes two inputs: bucket name and script path.  
**What it does:** On the server, AWS runs: get the file from S3, run it with Python. Whatever the script prints is what the Lambda reads.  
**Why:** This is how we run something on the server **without SSH** — AWS runs it for us and gives us the output.

---

### 3.4 S3 — “The script that detects the databases”

**Show:** S3 → your bucket → open folder *ssm* → open *discovery_python.py* (or just show the key in the list).

**Say:**  
*"The **script** lives here. When the document runs on the server, it downloads this file and runs it. The script only **looks** at the server: is MySQL running? Postgres? MongoDB? It reads versions and ports and prints **one line** of JSON. No passwords, no changes to the server — just read and report. That one line is what the Lambda gets and turns into the rows in the table."*

**What we did here:** Wrote a Python script and uploaded it here. The document (previous screen) points to this file.  
**What the code does:** Checks running processes and ports for MySQL, Postgres, MongoDB; gets version and port; prints one JSON line with “discovery_status” and “databases” list.  
**Why:** So the server does only the “looking” part; the Lambda does the “save and serve” part.

---

### 3.5 EC2 / Fleet Manager — “The server we run on”

**Show:** EC2 → Instances (one instance running) **or** Fleet Manager → instance **Online**.

**Say:**  
*"This is the **server** we run the script on. It's a normal EC2 instance. We gave it a **role** so it can talk to AWS and download the script from S3. We didn't open SSH; we just made sure it's **managed** by AWS (so the document can run on it). When the Lambda says 'run the document on this instance,' AWS does it and gives the output back."*

**What we did here:** One EC2 instance; attached a role that can use AWS (SSM) and read from S3.  
**What it does:** Registers with AWS so it appears in “managed instances”; when we run the document, this is where it runs.  
**Why:** We need at least one server that AWS can run the script on; this is that server.

---

### 3.6 Lambda — db-discovery-api — “What serves the data”

**Show:** Lambda → *db-discovery-api* → Code tab (show it's Python), briefly show handler.

**Say:**  
*"This is the **API** Lambda. It **doesn't run discovery**; it only **reads** the table. When someone calls a URL like /health or /accounts/123/instances, API Gateway calls this Lambda. The **code** looks at the path: if it's /health, it counts rows and returns 'ok'; if it's /accounts/…/instances, it reads rows for that account, groups them by server, and returns JSON. So the same data you saw in the table is what the API returns."*

**What we did here:** Wrote Python that reads from the same DynamoDB table and returns JSON depending on the path.  
**What the code does:** Gets the path from the request → if /health: scan table, return count; if /accounts/{id}/instances: query by account, group by instance, return list.  
**Why:** So tools and dashboards can get the data by calling a URL instead of opening the AWS console.

---

### 3.7 API Gateway — “The URL that calls the API Lambda”

**Show:** API Gateway → your API → Resources (show /health and /accounts/{accountId}/instances with GET).

**Say:**  
*"This is **how the API gets a URL**. We created routes: **/health** and **/accounts/{accountId}/instances**. Each route is a GET that calls the **db-discovery-api** Lambda. So when someone opens the URL in a browser or a tool, API Gateway receives it, calls the Lambda, and returns whatever the Lambda returns. No auth for this demo so we can call it from the browser."*

**What we did here:** Created an API and two routes; both use the same Lambda (proxy: request goes to Lambda as-is).  
**What it does:** Receives the HTTP request, invokes the API Lambda with the path and parameters, returns the Lambda's response.  
**Why:** So we have a stable, public URL (e.g. for dashboards or scripts) instead of calling the Lambda directly.

---

### 3.8 Browser — “Same data, as an API”

**Show:** Browser → your API URL + `/health`, then + `/accounts/YOUR_ACCOUNT_ID/instances`.

**Say:**  
*"Same data we saw in the table — now as **JSON from a URL**. /health says we're up and how many records we have. /accounts/…/instances gives the list of servers and their databases for that account. So the **full flow** is: discovery Lambda runs the script on the server → script output goes to the table → API Lambda reads the table and answers these URLs. One story, no disconnect."*

**What we did here:** Nothing — we're just calling the URL that API Gateway exposes.  
**What it does:** Shows the JSON response from the API Lambda (which read from DynamoDB).  
**Why:** To prove the end-to-end flow: table → API → URL.

---

# Chapter 4 — Flow in one line (to remember the connection)

*"Table stores results → discovery Lambda fills it by running a script on the server (script from S3, run via SSM) → API Lambda reads the table → API Gateway gives us a URL → browser or any tool calls that URL and gets the same data."*

---

# Chapter 5 — If they ask (short answers)

**Permissions:**  
*"Three roles: our Lambda can act in the other account and write the table; the other account's role only lets us list servers and run that one command; the server's role only lets it talk to AWS and download the script. No SSH keys."*

**Cross-account:**  
*"We have one list of account IDs. Each account has the same role and trusts us. Add or remove an account = edit the list and run discovery again. Same table, same API."*

**Other databases (Oracle, RDS, etc.):**  
*"Today we only detect MySQL, Postgres, Mongo on the server. To add more on the same servers we'd add a bit to the script and upload it again. For cloud DBs like RDS we'd call AWS APIs from the Lambda and write the same table — same API."*

---

# Chapter 6 — Checklists & readiness

## 6.0 45-minute presentation guide — Do I have enough to say?

**Yes.** Use this timeline so you don’t run short and don’t rush.

### Suggested timeline (total ~45 min)

| Block | What | Minutes |
|--------|--------|--------|
| **Intro** | Title + problem in one sentence (“We need to know what DBs run on our EC2s across accounts, without SSH”) + high-level flow in one line (Chapter 4). | **5** |
| **Screens 3.1–3.8** | Go through each screen: Show → Say (script) → briefly “What we did / Why.” Aim **3–4 min per screen** (e.g. 30–35 sec for “Say”, rest for clicking, pointing at fields, one “what we did” sentence). | **28–32** |
| **Live moment** | At 3.2: click **Test** on the discovery Lambda, wait ~30–60 s, then go back to DynamoDB (3.1) and **Scan** again — “See, new or updated rows.” Adds impact. | **(included above)** |
| **Recap** | Repeat the one-line flow (Chapter 4). “So: table → discovery fills it via SSM → API reads it → URL.” | **2** |
| **What’s next / limitations** | One slide or 3–4 sentences: “POC today. For production: auth on the API, schedule discovery (e.g. EventBridge), add more DB types or RDS from APIs.” | **3** |
| **Q&A** | Use Chapter 5 for short answers. Leave **5–7 min** for questions. | **5–7** |

**Total:** 5 + 28–32 + 2 + 3 + 5–7 ≈ **43–49 min** (adjust by speaking a bit more or less per screen).

---

### Optional “stretch” content (if you have extra time or someone asks)

Use these to go deeper on a screen so you fill 45 min comfortably:

- **3.1 DynamoDB:** Point out partition key `account_id`, sort key `instance_db_id` — “so we can query by account.” Show one item’s fields (instance_type, tags, databases list).
- **3.2 Discovery Lambda:** Scroll to the bit where it **assumes the spoke role** and **SendCommand** — “we never store SSH keys; we use IAM and assume role.” Mention “we could trigger this on a schedule with EventBridge.”
- **3.3 SSM document:** “Two parameters: bucket and script path. Same document for every account; we just pass different buckets if needed.”
- **3.4 S3 script:** “One script, versioned here. Change detection logic → upload new version → next discovery uses it.”
- **3.5 EC2/Fleet Manager:** “This instance has a role that allows SSM and S3 read. No SSH; that’s why it shows as managed and Online.”
- **3.6 API Lambda:** “One Lambda, path-based routing: /health, /accounts, /accounts/…/instances, /databases. All read from the same table.”
- **3.7 API Gateway:** “We could add API key or authorizer for production; for the demo it’s open so we can hit it from the browser.”
- **3.8 Browser:** Call **/accounts** as well — “list of account IDs that have discovery data.” Then **/accounts/{id}/instances** — “same structure the API Lambda builds from the table.”

If you use a couple of these per screen when you have time, you’ll have **enough content to fill 45 minutes** without stretching thin.

---

## 6.1 Quick checklist before you present

- [ ] EC2 **running**, instance **Online** in Fleet Manager  
- [ ] Tabs open in order: DynamoDB, Lambda db-discovery, SSM, S3, Lambda db-discovery-api, API Gateway, Browser  
- [ ] Your values filled (API URL, account ID) — see §1.1

---

## 6.2 Is everything covered? (if you're nervous)

**Yes.** You have:

- **Full flow:** DynamoDB → discovery Lambda → SSM document → S3 script → EC2/Fleet Manager → API Lambda → API Gateway → Browser. Each step is in **Chapter 3** with “Show / Say / What we did / Why.”
- **Quick reference:** **§1.2** tells you “what to show next” and “where to access” so you can glance and continue.
- **One-line story:** **Chapter 4** — memorize it.
- **If they ask:** **Chapter 5** — short answers for permissions, cross-account, and “other databases.”

**If you mem this and present:** You're not just clicking — you're telling a clear story (data → who fills it → what runs where → how it's exposed). Memorize the **one-line flow** and the **order of the 8 steps** (3.1–3.8); use the table in §1.2 when you forget where to click. Confidence + clear story + working demo = strong impression. Good luck — you've got the full story, chapter by chapter.
