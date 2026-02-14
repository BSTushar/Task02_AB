# Demo — Baby Steps (Click-by-Click)

Do exactly what each line says. Replace **YOUR_API_ID**, **YOUR_REGION**, **YOUR_SPOKE_ACCOUNT_ID** with your real values when you see them.

**API type:** **REST** over **HTTP(S)** — request/response, no WebSocket. (When creating the API in API Gateway, you choose **REST API**, not HTTP API or WebSocket.)

---

# PART A — Get your API URL (do this once)

1. Open your browser.
2. Go to: **https://console.aws.amazon.com**
3. Log in to your **management** AWS account.
4. Top-right: click the **region** dropdown (e.g. "N. Virginia" or "eu-west-1").
5. Select your region (e.g. **eu-west-1**).
6. Top-left: click **Services** (or the search box).
7. Type: **API Gateway**
8. Click **API Gateway** in the results.
9. Left sidebar: click **APIs** (or "API Gateway" → "APIs").
10. In the list, click your API name (e.g. **db-discovery-api**).
11. Left sidebar: click **Stages**.
12. Click the stage **prod**.
13. At the top you see **Invoke URL**. It looks like:  
    `https://abc123xyz.execute-api.eu-west-1.amazonaws.com/prod`
14. Copy that URL. The part before `.execute-api` is **YOUR_API_ID** (e.g. `abc123xyz`). The part after `execute-api.` and before `.amazonaws` is **YOUR_REGION** (e.g. `eu-west-1`).
15. Write them down:
    - **YOUR_API_ID** = _________________
    - **YOUR_REGION** = _________________
    - **YOUR_SPOKE_ACCOUNT_ID** = _________________ (your spoke/member account ID, 12 digits)

---

# PART B — Trigger discovery (Lambda)

1. In the browser, top-left: click **Services** (or the search box).
2. Type: **Lambda**
3. Click **Lambda** in the results.
4. Left sidebar: click **Functions**.
5. In the list of functions, click **db-discovery**.
6. You are now on the function page. You see tabs: **Code** | **Test** | **Configuration** | **Monitoring** | ...
7. Click the **Test** tab.
8. If you see **"Create new event"** or **"Configure test event"** or **"Test"** dropdown:
   - Click **"Create new event"** (or open the **Test** dropdown and choose **Configure test event**).
   - In the field **Event name**, type: **demo**
   - In the big text box labeled **Event JSON**, select all (Ctrl+A), delete, then paste exactly (nothing else):
     ```json
     {}
     ```
   - At the bottom, click **Save**.
9. You should now see an orange **Test** button. Click **Test** once.
10. Wait. It can take 30–90 seconds. Do not refresh.
11. When it finishes, you see **Execution result** at the top.
12. Check: **Status** should be **Succeeded** (green).
13. In the **Response** box you should see something like:
    ```json
    {"statusCode":200,"body":"{\"discovered\": 5, \"accounts\": [\"222222222222\"]}"}
    ```
14. (Optional) To show logs: click **View CloudWatch logs** or the **Logs** tab and point to lines like "Starting discovery", "discovered".

**Say:** "Discovery ran. This number is how many records were stored."

---

# PART C — Show SSM command (in spoke account)

1. Top-right: if you are in the **management** account, switch to the **spoke/member** account (account switcher dropdown).
2. Top-left: click **Services**, type: **Systems Manager**
3. Click **Systems Manager**.
4. Left sidebar: scroll and find **Node Management** (or **Fleet Manager**).
5. Click **Fleet Manager** (or **Run Command**).
6. If you see **Run command** in the left menu, click it. Otherwise look for **Command history**.
7. Click **Command history** (or the tab that shows past commands).
8. In the list, find the **most recent** command. **Document name** should be **DBDiscovery**. **Requested at** should match the time you clicked Test in Part B.
9. Click the **Command ID** (the link in the first column).
10. You see a list of **Instance ID** and **Status** (Success / Failed / etc.).
11. Point to it and say: "The command ran on each instance; we don't use SSH."

---

# PART D — Show DynamoDB (back in management account)

1. Top-right: switch back to the **management** account if needed.
2. Top-left: **Services** → type: **DynamoDB**
3. Click **DynamoDB**.
4. Left sidebar: click **Tables** (under "Data management" or similar).
5. In the list of tables, click **db-discovery-results**.
6. You see tabs like **Overview** | **Explore table items** | **Indexes** | ...
7. Click **Explore table items**.
8. You see a list of rows (items). Each row has **account_id** and **instance_db_id**.
9. Click **one row** (click anywhere on the row, or click the **instance_db_id** value, or the small arrow on the left to expand). The row expands and you see all attributes (instance_type, tags, engine, version, etc.).
10. Point to these and say what they are:
    - **account_id** — "Account where we discovered."
    - **instance_id** — "EC2 instance."
    - **instance_type** — "T-shirt size, e.g. t3.medium."
    - **tags** — "EC2 tags we capture (Name, Environment, etc.)."
    - **engine**, **version**, **port**, **data_size_mb** — "Database we found."
    - **discovery_status** — "Success or failed."
    - **discovery_timestamp** — "When we ran discovery."

**Say:** "We store instance type and tags so the API can expose them."

---

# PART E — Show the REST API (terminal / PowerShell)

Open **PowerShell** (or Command Prompt, or a terminal). You will paste one command at a time and press Enter.

**Replace in the commands below:**
- `YOUR_API_ID` → the value you wrote in Part A (e.g. abc123xyz)
- `YOUR_REGION` → the value you wrote (e.g. eu-west-1)
- `YOUR_SPOKE_ACCOUNT_ID` → your 12-digit spoke account ID

---

## E1 — Health

1. Copy this line (replace YOUR_API_ID and YOUR_REGION first):
   ```
   curl -s "https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com/prod/health"
   ```
2. Paste into PowerShell (or terminal).
3. Press **Enter**.
4. You should see: `{"status":"ok","total_records":N}`

**Say:** "Health check and total records."

---

## E2 — List accounts

1. Copy this line (replace YOUR_*):
   ```
   curl -s "https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com/prod/accounts"
   ```
2. Paste. Press **Enter**.
3. You should see: `{"accounts":["222222222222",...]}`

**Say:** "Accounts that have discovery data."

---

## E3 — Instances with instance_type and tags

1. Copy this line (replace all three placeholders):
   ```
   curl -s "https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com/prod/accounts/YOUR_SPOKE_ACCOUNT_ID/instances"
   ```
2. Paste. Press **Enter**.
3. You should see JSON with **instance_id**, **instance_type**, **tags**, **databases**, etc.

**Say:** "Per account we expose instances with t-shirt size and tags, plus databases."

---

## E4 — All databases (optional)

1. Copy:
   ```
   curl -s "https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com/prod/databases"
   ```
2. Paste. Press **Enter**.
3. You see the full list. Optionally try with filter:
   ```
   curl -s "https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com/prod/databases?engine=mysql"
   ```

**Say:** "Same data can be filtered for dashboards or CMDB."

---

# If you use PowerShell and "curl" doesn't work

On Windows, `curl` might be an alias. Try **curl.exe** first, e.g.:
```powershell
curl.exe -s "https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com/prod/health"
```

Or use **Invoke-RestMethod** (replace YOUR_* first, run one by one):

```powershell
$base = "https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com/prod"
Invoke-RestMethod "$base/health"
Invoke-RestMethod "$base/accounts"
Invoke-RestMethod "$base/accounts/YOUR_SPOKE_ACCOUNT_ID/instances"
Invoke-RestMethod "$base/databases"
```

---

# PART F — Optional: show a failed record

1. Go back to DynamoDB (Part D): **Services** → **DynamoDB** → **Tables** → **db-discovery-results** → **Explore table items**.
2. Scroll or scan the list for an item where **discovery_status** = **failed** or **db_id** = **discovery_failed**.
3. Click that row and show the **error** field if present.
4. **Say:** "Failed runs are still stored so we don't lose visibility."

---

# PART G — Wrap-up (what to say)

"We showed: trigger discovery from the management account, SSM running the script on EC2, results in DynamoDB including **tags** and **instance type**, and a REST API that exposes everything. Limitations: only SSM-managed instances, MySQL/PostgreSQL/MongoDB, batch discovery, single region. For production we'd add auth, retries, and pagination."

---

# Quick checklist (tick as you do it)

- [ ] Part A: Got API URL and wrote YOUR_API_ID, YOUR_REGION, YOUR_SPOKE_ACCOUNT_ID
- [ ] Part B: Lambda → Functions → db-discovery → Test tab → Test → Succeeded, saw "discovered"
- [ ] Part C: Switched to spoke → Systems Manager → Fleet Manager / Run command → Command history → DBDiscovery command
- [ ] Part D: Back to management → DynamoDB → Tables → db-discovery-results → Explore table items → showed instance_type + tags
- [ ] Part E: Ran curl (or Invoke-RestMethod) for /health, /accounts, /accounts/.../instances, /databases
- [ ] Part F (optional): Showed a failed record in DynamoDB
- [ ] Part G: Said wrap-up and limitations
