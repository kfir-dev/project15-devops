import json
from pathlib import Path
from urllib.parse import urlsplit

EXPECTED = {"/health/live", "/health/ready", "/api/products"}
PARENTS = {"", "/", "/health", "/api"}

def zap_pre_shutdown(zap):
    output = Path("/zap/wrk/zap-coverage.json")
    try:
        total = int(zap.core.number_of_messages())
        if total > 1000:
            raise ValueError("History exceeds bounded inspection limit.")
        observed = []
        virtual_parents = []
        unexpected_operations = []
        unsafe_methods = 0

        for start in range(0, total, 100):
            for message in zap.core.messages(start=start, count=100):
                lines = message.get("requestHeader", "").splitlines()
                parts = lines[0].split() if lines else []
                if len(parts) < 2:
                    continue
                method, target = parts[:2]
                if target.startswith("/"):
                    host = next(
                        (line.split(":", 1)[1].strip() for line in lines[1:]
                         if line.lower().startswith("host:")), ""
                    )
                    target = "http://" + host + target
                parsed = urlsplit(target)
                if parsed.hostname != "project15.local":
                    continue

                response_header = message.get("responseHeader", "")
                response = response_header.splitlines()
                status = int(response[0].split()[1]) if response else 0
                history_type = str(message.get("type", "unknown"))
                operation = {
                    "method": method, "path": parsed.path,
                    "status": status, "history_type": history_type,
                }

                if (history_type == "0" and method == "GET"
                        and parsed.path in PARENTS and not parsed.query
                        and not message.get('responseBody', '') and status == 0):
                    virtual_parents.append(operation)
                    continue

                if method != "GET":
                    unsafe_methods += 1
                if parsed.path not in EXPECTED:
                    unexpected_operations.append(operation)
                    continue
                observed.append(operation)

        report = {
            "mode": "passive",
            "observed": observed,
            "virtual_parent_records": virtual_parents,
            "virtual_parent_count": len(virtual_parents),
            "unsafe_method_count": unsafe_methods,
            "unexpected_path_count": len(unexpected_operations),
            "unexpected_operations": unexpected_operations,
            "passive_records_remaining": int(zap.pscan.records_to_scan),
            "active_scan_count": len(zap.ascan.scans),
            "inspected_message_count": total,
        }
    except Exception as exc:
        report = {"error": type(exc).__name__}
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    output.chmod(0o600)
