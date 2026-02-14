# Quick Defense Cheat Sheet - Database Discovery POC

**Use this for quick review before your presentation.**

---

## 🎯 WHY THIS ARCHITECTURE?

| Question | Key Answer |
|----------|------------|
| **Hub-and-spoke?** | Centralized management, security boundaries, scalable, auditable |
| **SSM instead of SSH?** | No keys, no open ports, IAM-based, auditable, compliant |
| **DynamoDB instead of RDS?** | Serverless, auto-scales, no connection management, cost-effective |
| **Lambda instead of EC2?** | Event-driven, pay-per-use, no infrastructure, auto-scaling |
| **S3 for script?** | Version control, separation of concerns, reusability |

---

## ⚠️ LIMITATIONS (Be Honest!)

1. **SSM-managed instances only** → Unmanaged instances invisible
2. **3 database engines** → MySQL, PostgreSQL, MongoDB only
3. **Batch discovery** → Not real-time, data can be stale
4. **Single region** → Multi-region requires multiple deployments
5. **No containers** → Containerized DBs not detected
6. **No RDS** → Only EC2-installed databases
7. **DynamoDB Scan** → Slow for large tables (needs GSI)
8. **No API auth** → Public endpoints (POC only)

---

## ✅ BENEFITS

- ✅ **Security**: IAM-based, no credentials, auditable
- ✅ **Scalable**: Serverless auto-scales
- ✅ **Cost**: <$1/month for 1000 instances
- ✅ **Simple**: No infrastructure to manage
- ✅ **Flexible**: Easy to extend

---

## ❌ DISADVANTAGES

- ❌ SSM dependency (requires agent)
- ❌ Batch processing (not real-time)
- ❌ Limited database coverage
- ❌ Single region
- ❌ No container support
- ❌ Scan performance issues
- ❌ No API authentication

---

## 🔒 SECURITY DEFENSE

**Key Points:**
1. **IAM Least Privilege**: Each role has minimal permissions
2. **No Credentials**: Temporary STS tokens, no SSH keys
3. **Read-Only**: No database connections, no config changes
4. **Auditable**: All actions in CloudTrail
5. **Network**: Outbound HTTPS only, no inbound ports

**S3 Script Risk:**
- **Acknowledge**: Script tampering is a risk
- **Current**: S3 access restricted
- **Production**: Would add versioning, signing, checksums

---

## 📈 SCALABILITY

**What Breaks First:**
1. SSM rate limits (~60 commands/sec)
2. Lambda timeout (15 min max)
3. DynamoDB Scan (O(n) operation)

**Solutions:**
- Batch instances per command
- Parallel account processing
- Add GSI for queries
- Chunk large fleets

**Capacity:**
- **Current**: ~100-200 instances/account
- **Optimized**: 1000+ instances/account

---

## 💰 COST

**Breakdown:**
- Lambda: ~$0.60/month (negligible)
- DynamoDB: ~$0.04/month (negligible)
- SSM: Free
- S3: ~$0.01/month (negligible)
- API Gateway: ~$0.04/month (negligible)

**Total: <$1/month for 1000 instances**

**Why Cheap?**
- Serverless (no idle costs)
- Pay-per-use
- Low request volume

---

## 🛠️ TECHNICAL DECISIONS

| Decision | Why |
|----------|-----|
| **Python** | Readable, standard library, AWS SDK, common on Linux |
| **JSON output** | Structured, easy to parse, SSM-friendly |
| **On-demand DynamoDB** | Auto-scales, no capacity planning, variable workload |

---

## 🚨 FAILURE HANDLING

**Failure Types & Handling:**

1. **Assume Role Fails** → Account skipped, logged
2. **SSM Command Fails** → Record with `discovery_status: "failed"`
3. **Script Fails** → Error JSON returned, stored
4. **DynamoDB Fails** → Lambda fails, logged (no retry in POC)
5. **Lambda Timeout** → Partial results, increase timeout
6. **Instance Terminates** → Record with failed status

**Key Principle**: Failures are isolated; one failure doesn't break entire discovery.

---

## 🚀 PRODUCTION CHANGES

**Critical:**
1. API authentication (IAM/API keys)
2. DynamoDB GSI + pagination
3. DLQ + retry logic
4. CloudWatch metrics + alarms
5. S3 script signing

**Nice to Have:**
- Multi-region support
- Container discovery
- RDS/Aurora discovery
- Historical tracking (TTL)

---

## 💬 COMMON CHALLENGES

**"Over-engineered?"**
→ Balances simplicity with production needs. Simpler approaches have security/scalability issues.

**"Why not AWS Config/SSM Inventory?"**
→ Don't support custom scripts or running process detection. Need flexibility.

**"What if no Python 3?"**
→ Known limitation. Document requirement or provide bash alternative.

**"Multi-region?"**
→ Single-region for POC. Production: deploy Lambda per region.

**"Containers?"**
→ Out of scope. Can be added as Phase 2.

---

## 🎤 PRESENTATION TIPS

**Opening:**
- "This is a proof-of-concept for automated database discovery across AWS accounts."
- "We chose serverless architecture for security, scalability, and cost-effectiveness."

**When Asked About Limitations:**
- Acknowledge honestly
- Explain why acceptable for POC
- Show you know what needs to change for production

**When Challenged:**
- Don't get defensive
- Explain trade-offs
- Show you've considered alternatives
- Demonstrate production thinking

**Closing:**
- "This POC demonstrates the foundation for production-ready discovery."
- "Key next steps: authentication, GSI, retries, multi-region."

---

## 🔑 KEY MESSAGES TO EMPHASIZE

1. ✅ **Security First**: IAM-based, no credentials, auditable
2. ✅ **Scalable Foundation**: Can handle growth
3. ✅ **Cost-Effective**: <$1/month for 1000 instances
4. ✅ **Production-Ready Foundation**: Can be hardened
5. ✅ **Honest About Limitations**: Know what needs improvement

---

## ⚡ QUICK ANSWERS (Memorize These!)

**Q: Why SSM?**
A: No SSH keys, IAM-based, auditable, no open ports.

**Q: Why DynamoDB?**
A: Serverless, auto-scales, no connection management, cost-effective.

**Q: Why Lambda?**
A: Event-driven, pay-per-use, no infrastructure, auto-scaling.

**Q: What breaks at scale?**
A: SSM rate limits, Lambda timeout, DynamoDB Scan. Solutions: batching, GSI, chunking.

**Q: What's the cost?**
A: <$1/month for 1000 instances. Serverless = pay-per-use.

**Q: What are limitations?**
A: SSM-managed only, 3 engines, batch discovery, single region. All documented and can be extended.

**Q: Is it production-ready?**
A: Foundation is solid. Needs: auth, GSI, retries, monitoring. POC demonstrates feasibility.

---

**Remember**: Confidence = Understanding trade-offs + Honest about limitations + Production thinking
