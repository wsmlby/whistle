# Test cases for whistle log analysis
# Each test case is a dict with log, expected anomaly, and expected reason substring

test_cases = [
    {
        "log": "Aug 26 10:00:00 server sshd[1234]: Failed password for root from 192.168.1.100 port 22 ssh2",
        "expect_anomaly": True,
        "expect_reason_contains": ["password", "authentication", "login attempt"]
    },
    {
        "log": "Aug 26 10:01:00 server systemd[1]: Started WhistleAI Log Monitoring Service.",
        "expect_anomaly": False
    },
    {
        "log": "Aug 26 10:02:00 server kernel: [12345.678901] CPU temperature above threshold, cpu clock throttled",
        "expect_anomaly": True,
        "expect_reason_contains": ["temperature", "overheat"]
    },
    {
        "log": "Aug 26 10:03:00 server nginx[5678]: 404 Not Found: /favicon.ico",
        "expect_anomaly": False
    },
    {
        "log": "Aug 26 10:03:10 server nginx[5678]: 404 Not Found: /favicon.ico",
        "expect_ignored": True
    }
]
