---
name: Performance Issue
about: Report high latency, database lock contention, or resource saturation
title: "[PERF] "
labels: ["performance"]
assignees: ''
---

**Performance Metric Concerned**
- [ ] End-to-End Latency (HTTP response time > budget)
- [ ] SQLite Lock Contention / Timeout (`database is locked`)
- [ ] CPU / Memory Spikes
- [ ] Streaming TTFT (Time to First Token) Degradation

**Ava Version / Deployment Setup**
- Version:
- Hardware / Platform (e.g. 2 vCPU, 4GB RAM, NVMe SSD):
- Concurrent Users:
- SQLite Storage Mount (Local Disk vs Network Volume):

**Observed Latency / Metrics**
- Latency (ms):
- Request Path (`/api/chat`, `/api/chat/stream`, `/health`):

**Steps to Reproduce / Load Profile**
Describe the concurrency or load pattern leading to the issue.
