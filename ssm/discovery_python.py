#!/usr/bin/env python3
import json
import os
import re
import subprocess

def run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (subprocess.TimeoutExpired, Exception):
        return ""

def dir_size_mb(path):
    if os.path.isdir(path) and os.access(path, os.R_OK):
        out = run(f"du -sm {path} 2>/dev/null")
        return int(out.split()[0]) if out else 0
    return 0

def mem_mb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 0

def cpu_cores():
    try:
        with open("/proc/cpuinfo") as f:
            return len([l for l in f if l.startswith("processor")])
    except Exception:
        pass
    return 0

def extract_version(s):
    m = re.search(r'[0-9]+\.[0-9]+(?:\.[0-9]+)?', str(s))
    return m.group(0) if m else "unknown"

def get_port_for_proc(proc_name, default):
    out = run("ss -tlnp 2>/dev/null")
    for line in out.split("\n"):
        if f":{default} " in line and proc_name in line:
            parts = line.split()
            for p in parts:
                if ":" in p and p.split(":")[-1].isdigit():
                    return int(p.split(":")[-1])
    return default

def main():
    try:
        mem = mem_mb()
        cpu = cpu_cores()
        databases = []

        if run("pgrep -f mysqld"):
            ver = extract_version(run("mysql --version 2>/dev/null") or run("mysqld --version 2>/dev/null"))
            size = dir_size_mb("/var/lib/mysql") or dir_size_mb("/var/lib/mysql/data")
            port = get_port_for_proc("mysqld", 3306)
            databases.append({
                "db_id": f"mysql-{port}", "engine": "mysql", "version": ver, "status": "running",
                "port": port, "data_size_mb": size, "system_memory_mb": mem, "system_cpu_cores": cpu
            })
        elif run("command -v mysql") or run("command -v mysqld"):
            ver = extract_version(run("mysql --version 2>/dev/null") or run("mysqld --version 2>/dev/null"))
            databases.append({
                "db_id": "mysql-3306", "engine": "mysql", "version": ver, "status": "installed",
                "port": 3306, "data_size_mb": 0, "system_memory_mb": mem, "system_cpu_cores": cpu
            })

        if run("pgrep -f postgres"):
            ver = extract_version(run("psql --version 2>/dev/null") or run("postgres --version 2>/dev/null"))
            size = dir_size_mb("/var/lib/postgresql/data") or dir_size_mb("/var/lib/pgsql/data")
            port = get_port_for_proc("postgres", 5432)
            databases.append({
                "db_id": f"postgres-{port}", "engine": "postgresql", "version": ver, "status": "running",
                "port": port, "data_size_mb": size, "system_memory_mb": mem, "system_cpu_cores": cpu
            })
        elif run("command -v psql") or run("command -v postgres"):
            ver = extract_version(run("psql --version 2>/dev/null") or run("postgres --version 2>/dev/null"))
            databases.append({
                "db_id": "postgres-5432", "engine": "postgresql", "version": ver, "status": "installed",
                "port": 5432, "data_size_mb": 0, "system_memory_mb": mem, "system_cpu_cores": cpu
            })

        if run("pgrep -f mongod"):
            ver = extract_version(run("mongod --version 2>/dev/null"))
            size = dir_size_mb("/var/lib/mongodb") or dir_size_mb("/data/db")
            port = get_port_for_proc("mongod", 27017)
            databases.append({
                "db_id": f"mongodb-{port}", "engine": "mongodb", "version": ver, "status": "running",
                "port": port, "data_size_mb": size, "system_memory_mb": mem, "system_cpu_cores": cpu
            })
        elif run("command -v mongod"):
            ver = extract_version(run("mongod --version 2>/dev/null"))
            databases.append({
                "db_id": "mongodb-27017", "engine": "mongodb", "version": ver, "status": "installed",
                "port": 27017, "data_size_mb": 0, "system_memory_mb": mem, "system_cpu_cores": cpu
            })

        out = {"discovery_status": "success", "system_memory_mb": mem, "system_cpu_cores": cpu, "databases": databases}
        print(json.dumps(out))
    except Exception as e:
        print(json.dumps({"discovery_status": "error", "error": str(e), "databases": []}))

if __name__ == "__main__":
    main()
