# Cloud Security & Infrastructure Architecture Specification

## Section 1: Network Topology & VPC Isolation
The infrastructure is deployed across multiple AWS regions with primary deployment in `us-east-1` and disaster recovery in `us-west-2`. Each region maintains three isolated Virtual Private Clouds (VPCs):
- **Edge VPC**: Houses Internet-facing Application Load Balancers (ALB) with AWS WAF v2 enabled for DDoS mitigation and SQL injection filtering.
- **Application VPC**: Houses containerized services orchestrated via Amazon Elastic Kubernetes Service (EKS). Compute nodes operate in private subnets with egress via dual NAT Gateways across distinct Availability Zones (`us-east-1a`, `us-east-1b`).
- **Data VPC**: Isolated database tier containing Amazon Aurora PostgreSQL multi-AZ clusters and Qdrant vector database clusters. Direct internet ingress and egress are strictly disabled; communication with the Application VPC occurs exclusively over AWS Transit Gateway and VPC Peering connections with security group mutual trust.

## Section 2: Identity & Access Management (IAM) and Authentication
- All service-to-service communications utilize short-lived IAM roles via AWS IRSA (IAM Roles for Service Accounts) with maximum token lifetime of 1 hour.
- Developer access to production environments is mediated via AWS IAM Identity Center (SSO) requiring hardware FIDO2 Multi-Factor Authentication (MFA).
- Break-glass emergency administrator access requires dual approvals from the Head of Infrastructure and CISO, triggering automated Slack and PagerDuty audit alerts.

## Section 3: Data Encryption Standards
- **Data at Rest**: All persistent volumes (EBS gp3), PostgreSQL databases, Redis cache instances, and S3 object storage buckets are encrypted using AWS KMS Customer Managed Keys (CMK) with AES-256-GCM. KMS key rotation is automatically scheduled every 365 days.
- **Data in Transit**: Enforced TLS 1.3 for all external HTTP traffic; internal microservice communication is encrypted using mTLS with certificates issued by AWS Private Certificate Authority (PCA) and rotated every 30 days.

## Section 4: Disaster Recovery & Replication
- Aurora PostgreSQL cross-region replication latency is maintained below 200 milliseconds under normal operating conditions.
- Vector store snapshots are synced to S3 with cross-region replication every 60 minutes.
- Recovery Point Objective (RPO) is established at 5 minutes; Recovery Time Objective (RTO) is established at 30 minutes for complete regional failover.
