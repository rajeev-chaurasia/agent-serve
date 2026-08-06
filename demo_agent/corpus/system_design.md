# System Design Reference

## Load Balancing

Load balancers distribute incoming traffic across multiple backend servers to improve
throughput, reduce latency, and eliminate single points of failure.

**Algorithms:**
- **Round-robin**: requests cycled evenly — simple, ignores server load.
- **Least connections**: routes to the server with fewest active connections.
- **IP hash**: consistent mapping from client IP to server — sticky sessions.
- **Weighted round-robin**: servers assigned weight proportional to capacity.

**Layer 4 vs Layer 7:**
- L4 (transport): routes on IP/TCP without inspecting payload. Faster, less flexible.
- L7 (application): routes on HTTP headers, URL, cookies. Enables content-aware routing.

Health checks: LB probes backends periodically; removes unhealthy nodes automatically.

## Caching

Caching stores computed results closer to the consumer to reduce latency and backend load.

**Strategies:**
- **Cache-aside (lazy loading)**: app checks cache → miss → fetch DB → populate cache.
- **Write-through**: write to cache and DB simultaneously. Cache always consistent.
- **Write-behind (write-back)**: write to cache, async flush to DB. Risk of data loss.
- **Read-through**: cache sits in front of DB; app always talks to cache.

**Eviction policies:** LRU (Least Recently Used), LFU (Least Frequently Used), TTL-based.

**Thundering herd**: many cache misses simultaneously overwhelm the origin.
Mitigation: mutex/lock-on-miss, probabilistic early expiration, background refresh.

Cache invalidation is famously hard — stale data vs. consistency trade-off.

## CAP Theorem

A distributed system can guarantee at most two of:
- **Consistency (C)**: every read sees the most recent write.
- **Availability (A)**: every request receives a (non-error) response.
- **Partition tolerance (P)**: system continues operating despite network partitions.

Since network partitions are unavoidable in practice, the real choice is CP vs AP:
- **CP systems** (HBase, Zookeeper): sacrifice availability under partition.
- **AP systems** (Cassandra, DynamoDB): sacrifice consistency (eventual consistency).

PACELC extends CAP: even without partitions, there's a latency vs. consistency trade-off.

## Message Queues

Message queues decouple producers from consumers, enabling async processing and buffering.

**Common systems:** RabbitMQ (AMQP), Apache Kafka, AWS SQS, Redis Streams.

**Key concepts:**
- **At-most-once**: message delivered 0 or 1 times (fire-and-forget, possible loss).
- **At-least-once**: message delivered 1 or more times (duplicates possible).
- **Exactly-once**: hardest guarantee, requires idempotent consumers or transactions.

**Kafka specifics:**
- Topics partitioned across brokers; each partition is an append-only log.
- Consumer groups: each partition consumed by exactly one consumer in a group.
- Retention: messages kept for a configurable period, not deleted on consumption.
- Throughput: millions of messages/sec; designed for high-throughput event streaming.

**Use cases:** async job processing, event sourcing, log aggregation, microservice decoupling.
