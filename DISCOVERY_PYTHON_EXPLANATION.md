# Discovery Python Script - Comprehensive Explanation

## 📋 Overview

The `discovery_python.py` script is a **read-only database discovery tool** that runs on EC2 instances via AWS Systems Manager (SSM). It automatically detects installed database engines (MySQL, PostgreSQL, MongoDB), collects their metadata, and outputs structured JSON results.

### Purpose in the Architecture

```
Management Account Lambda → SSM Run Command → EC2 Instance → discovery_python.py → JSON Output → DynamoDB
```

This script is executed remotely on EC2 instances without requiring SSH access, making it secure and scalable for cross-account discovery.

---

## 🔍 What It Discovers

1. **Database Engines**: MySQL, PostgreSQL, MongoDB
2. **Database Status**: Running vs. Installed (but not running)
3. **Database Version**: Extracted from version commands
4. **Database Port**: Actual listening port (not just default)
5. **Data Size**: Size of database data directories in MB
6. **System Resources**: Total memory (MB) and CPU cores

---

## 📚 Code Structure - Function by Function

### 1. `run(cmd)` - Safe Command Execution
```python
def run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (subprocess.TimeoutExpired, Exception):
        return ""
```

**Purpose**: Executes shell commands safely with error handling.

**Key Features**:
- **5-second timeout**: Prevents hanging on slow/failed commands
- **Error suppression**: Returns empty string on failure (no crashes)
- **Text output**: Returns clean string output, not bytes

**Why it matters**: The script runs in various environments. Some commands might fail (missing binaries, permission issues). This function ensures the script continues even if individual checks fail.

---

### 2. `dir_size_mb(path)` - Directory Size Calculation
```python
def dir_size_mb(path):
    if os.path.isdir(path) and os.access(path, os.R_OK):
        out = run(f"du -sm {path} 2>/dev/null")
        return int(out.split()[0]) if out else 0
    return 0
```

**Purpose**: Calculates the size of database data directories.

**How it works**:
1. Checks if path exists and is readable
2. Uses `du -sm` (disk usage in MB, summary)
3. Parses the first number from output
4. Returns 0 if path doesn't exist or isn't readable

**Example**: `/var/lib/mysql` → `2048` (2GB)

**Why it matters**: Database sizing helps with capacity planning and cost estimation.

---

### 3. `mem_mb()` - System Memory Detection
```python
def mem_mb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 0
```

**Purpose**: Reads total system memory from Linux `/proc/meminfo`.

**How it works**:
- Opens `/proc/meminfo` (Linux kernel memory info)
- Finds `MemTotal:` line (e.g., "MemTotal: 8388608 kB")
- Converts from KB to MB (divide by 1024)

**Example**: `8388608 KB` → `8192 MB` (8GB)

**Why it matters**: System memory helps understand if instances are appropriately sized for their databases.

---

### 4. `cpu_cores()` - CPU Core Count
```python
def cpu_cores():
    try:
        with open("/proc/cpuinfo") as f:
            return len([l for l in f if l.startswith("processor")])
    except Exception:
        pass
    return 0
```

**Purpose**: Counts CPU cores by counting "processor" lines in `/proc/cpuinfo`.

**How it works**:
- Each CPU core has a "processor" line
- Counts these lines to get total cores

**Example**: 4 lines starting with "processor" → `4` cores

**Why it matters**: CPU cores indicate instance compute capacity.

---

### 5. `extract_version(s)` - Version String Parsing
```python
def extract_version(s):
    m = re.search(r'[0-9]+\.[0-9]+(?:\.[0-9]+)?', str(s))
    return m.group(0) if m else "unknown"
```

**Purpose**: Extracts version numbers from version command output.

**How it works**:
- Uses regex to find version pattern: `X.Y` or `X.Y.Z`
- Handles various output formats

**Examples**:
- `mysql  Ver 8.0.35 for Linux` → `8.0.35`
- `PostgreSQL 14.9` → `14.9`
- `db version v4.4.24` → `4.4.24`

**Why it matters**: Version information is critical for security patching and compatibility checks.

---

### 6. `get_port_for_proc(proc_name, default)` - Port Detection
```python
def get_port_for_proc(proc_name, default):
    out = run("ss -tlnp 2>/dev/null")
    for line in out.split("\n"):
        if f":{default} " in line and proc_name in line:
            parts = line.split()
            for p in parts:
                if ":" in p and p.split(":")[-1].isdigit():
                    return int(p.split(":")[-1])
    return default
```

**Purpose**: Finds the actual listening port for a database process.

**How it works**:
1. Runs `ss -tlnp` (list TCP listening ports with process names)
2. Searches for lines containing the default port AND process name
3. Extracts port number from the line
4. Falls back to default if not found

**Example**:
- MySQL default: 3306, but might be running on 3307
- Finds `:3307` with `mysqld` → returns `3307`

**Why it matters**: Databases might run on non-standard ports. This ensures accurate port detection.

---

## 🎯 Main Function Logic Flow

### Step 1: Collect System Information
```python
mem = mem_mb()      # System memory
cpu = cpu_cores()   # CPU cores
databases = []      # Empty list to collect database info
```

### Step 2: Check Each Database Engine

For each database (MySQL, PostgreSQL, MongoDB), the script follows this pattern:

#### Pattern A: Database is Running
```python
if run("pgrep -f mysqld"):  # Check if MySQL process is running
    ver = extract_version(...)           # Get version
    size = dir_size_mb(...)              # Get data size
    port = get_port_for_proc(...)        # Get actual port
    databases.append({
        "db_id": f"mysql-{port}",
        "engine": "mysql",
        "version": ver,
        "status": "running",             # ✅ Running
        "port": port,
        "data_size_mb": size,
        "system_memory_mb": mem,
        "system_cpu_cores": cpu
    })
```

#### Pattern B: Database is Installed (but not running)
```python
elif run("command -v mysql"):  # Check if MySQL binary exists
    ver = extract_version(...)
    databases.append({
        "db_id": "mysql-3306",
        "engine": "mysql",
        "version": ver,
        "status": "installed",           # ⚠️ Installed but not running
        "port": 3306,                    # Default port
        "data_size_mb": 0,               # Can't measure if not running
        ...
    })
```

**Key Distinction**:
- **Running**: Process detected → can get port, data size
- **Installed**: Binary exists → can get version, but port/data size unknown

### Step 3: Output JSON Results
```python
out = {
    "discovery_status": "success",
    "system_memory_mb": mem,
    "system_cpu_cores": cpu,
    "databases": databases
}
print(json.dumps(out))
```

**Success Output Example**:
```json
{
  "discovery_status": "success",
  "system_memory_mb": 8192,
  "system_cpu_cores": 4,
  "databases": [
    {
      "db_id": "mysql-3306",
      "engine": "mysql",
      "version": "8.0.35",
      "status": "running",
      "port": 3306,
      "data_size_mb": 2048,
      "system_memory_mb": 8192,
      "system_cpu_cores": 4
    }
  ]
}
```

**Error Output Example**:
```json
{
  "discovery_status": "error",
  "error": "Permission denied",
  "databases": []
}
```

---

## 🔐 Security & Safety Features

### 1. **Read-Only Operations**
- No database connections
- No configuration changes
- No data modifications
- Only reads system information

### 2. **Error Handling**
- Timeouts prevent hanging
- Graceful degradation (continues if one DB check fails)
- Returns structured error messages

### 3. **No Credentials Required**
- Doesn't connect to databases
- Uses system commands only
- Safe to run on any Linux instance

---

## 🚀 How It's Executed

### Via SSM Document
The script is uploaded to S3 and executed via SSM Run Command:

```json
{
  "mainSteps": [{
    "action": "aws:runShellScript",
    "inputs": {
      "runCommand": [
        "aws s3 cp s3://bucket/ssm/discovery_python.py /tmp/db_discovery.py",
        "python3 /tmp/db_discovery.py"
      ]
    }
  }]
}
```

### Execution Flow
1. Lambda function triggers SSM Run Command
2. SSM agent on EC2 downloads script from S3
3. Script executes locally on EC2
4. JSON output captured by SSM
5. Lambda retrieves output and stores in DynamoDB

---

## 📊 Output Schema

### Database Record Structure
```json
{
  "db_id": "mysql-3306",           // Unique identifier: engine-port
  "engine": "mysql",                // mysql | postgresql | mongodb
  "version": "8.0.35",              // Version string
  "status": "running",              // running | installed
  "port": 3306,                     // Listening port
  "data_size_mb": 2048,             // Database data size
  "system_memory_mb": 8192,         // Instance memory
  "system_cpu_cores": 4             // Instance CPU cores
}
```

---

## 🎓 Key Learning Points

### 1. **Process Detection**
- `pgrep -f process_name`: Checks if process is running
- `command -v binary`: Checks if binary is installed

### 2. **Linux System Information**
- `/proc/meminfo`: System memory information
- `/proc/cpuinfo`: CPU information
- `ss -tlnp`: Network port and process information
- `du -sm`: Directory size calculation

### 3. **Error Resilience**
- Always returns valid JSON (never crashes)
- Continues discovery even if one DB check fails
- Provides meaningful error messages

### 4. **Cross-Platform Considerations**
- Uses standard Linux commands (works on Amazon Linux, Ubuntu, etc.)
- Handles missing binaries gracefully
- Works in restricted environments

---

## 💡 Presentation Tips

### For Technical Audience
1. **Start with Architecture**: Show how it fits in the hub-spoke model
2. **Explain Security**: Emphasize read-only, no SSH, no credentials
3. **Show Code Flow**: Walk through main() function logic
4. **Demo Output**: Show real JSON examples

### For Business Audience
1. **Problem Statement**: "How do we discover databases across 100+ accounts?"
2. **Solution**: "Automated, secure, no manual access needed"
3. **Benefits**: Cost visibility, compliance, security patching
4. **Results**: Show dashboard/API examples

### Key Metrics to Highlight
- ✅ **Zero SSH access required**
- ✅ **Read-only operations** (safe)
- ✅ **Multi-database support** (MySQL, PostgreSQL, MongoDB)
- ✅ **Cross-account discovery** (scalable)
- ✅ **Structured output** (API-ready)

---

## 🔧 Common Scenarios

### Scenario 1: Multiple Databases on One Instance
```json
{
  "databases": [
    {"engine": "mysql", "status": "running", "port": 3306},
    {"engine": "postgresql", "status": "running", "port": 5432}
  ]
}
```

### Scenario 2: Database Installed but Not Running
```json
{
  "databases": [
    {"engine": "mysql", "status": "installed", "port": 3306, "data_size_mb": 0}
  ]
}
```

### Scenario 3: No Databases Found
```json
{
  "discovery_status": "success",
  "databases": []
}
```

---

## 🎯 Summary

The `discovery_python.py` script is a **lightweight, secure, and robust** database discovery tool that:

1. ✅ Detects MySQL, PostgreSQL, and MongoDB
2. ✅ Collects version, port, and sizing information
3. ✅ Provides system resource metrics
4. ✅ Outputs structured JSON for API consumption
5. ✅ Handles errors gracefully
6. ✅ Requires no database credentials or SSH access

It's designed to run remotely via SSM, making it perfect for automated discovery across multiple AWS accounts.
