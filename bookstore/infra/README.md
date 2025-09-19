
﻿# Infra: Bookstore Architecture (Bastion + Dual ALBs + Frontend/Backend + DynamoDB)

This CDK stack provisions the final bookstore infrastructure design:

High‑level goals:
- Strict network segmentation (public access only through a public ALB; backend reachable only through an internal ALB)
- One public bastion for SSH administration
- Isolated frontend and backend EC2 instances (each in its own private subnet group)
- Application Load Balancers:
	- Public ALB (HTTP 80) -> Frontend instance
	- Internal ALB (port 5001) -> Backend instance
- Environment variable wiring: frontend container gets `REACT_APP_API_BASE_URL` pointing to the internal backend ALB DNS
- DynamoDB table `tb_books` (PAY_PER_REQUEST)
- Use existing EC2 KeyPair (`KeyName` parameter, default `llave1.pem`)
- Reuse existing IAM role `LabRole` (imported, no inline policies added due to platform restrictions)

---
## Architecture Overview

```
								Internet
									 |
						(Public ALB :80)
									 |
						[ SG: SgAlbFront ]
									 |
				┌────────────────────────┐
				│  Frontend EC2 (private-front subnet)
				│  - Docker container (frontend)
				│  - Listens on :80 (via ALB target)
				│  - Env REACT_APP_API_BASE_URL=http://<backend-alb-dns>:5001
				└────────────────────────┘
									 |
				 (Allowed only SG to SG)
									 v
				 (Internal ALB :5001)  <— not Internet facing
									 |
						[ SG: SgAlbBack ]
									 |
				┌────────────────────────┐
				│ Backend EC2 (private-back subnet)
				│ - Docker container (backend)
				│ - Exposes :5001
				│ - Health check /healthz
				└────────────────────────┘

	Bastion EC2 (public subnet) --- SSH --> Frontend/Backend (only via SG rules)

	DynamoDB: tb_books (partition key: id)
```

Networking:
- VPC: up to 2 AZs
	- 1 public subnet group (for bastion + public ALB subnets)
	- 1 private-front subnet group
	- 1 private-back subnet group
- 1 NAT Gateway (egress for private instances)
- Backend internal ALB spans two private-back subnets (multi‑AZ requirement for ALB)

Security Groups (ingress summary):
- SgBastion: 22 from 0.0.0.0/0 (demo – tighten in production)
- SgAlbFront: 80 from 0.0.0.0/0
- SgFrontend: 80 from SgAlbFront; 22 from SgBastion
- SgAlbBack: 5001 from SgAlbFront (enforced after creation) – internal only
- SgBackend: 5001 from SgAlbBack; 22 from SgBastion

Environment Propagation:
- Frontend UserData runs container with:
	`docker run ... -e REACT_APP_API_BASE_URL=http://<backend-internal-alb-dns>:5001 ...`
	so React code uses the correct backend base URL.

IAM / Permissions Notes:
- We import existing role `LabRole`. In AWS Academy environments students typically cannot attach inline policies (`iam:PutRolePolicy` denied). Therefore we DO NOT call `grant_read_write_data` on the table. Ensure `LabRole` already has sufficient DynamoDB permissions, or data operations will fail at runtime.

---
## Parameters

| Parameter       | Default                                      | Purpose |
|-----------------|----------------------------------------------|---------|
| KeyName         | llave1.pem                                   | Existing EC2 KeyPair for SSH |
| BackendImage    | davidlondo/back-bookstore:latest             | Backend Docker image repo:tag |
| FrontendImage   | davidlondo/front-bookstore:v3                | Frontend Docker image repo:tag |

You can override any parameter at deploy time with `--parameters InfraStack:ParamName=value`.

---
## Prerequisites

- Node.js & AWS CDK CLI (`npm i -g aws-cdk@2`)
- Python 3.11+
- Existing KeyPair in the target region (e.g., `llave1` / `llave1.pem` locally)
- AWS credentials with permissions to create EC2, ALB, VPC, DynamoDB (IAM changes for `LabRole` are NOT required)

---
## Setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Bootstrap the environment once per account/region if not done already:
```
cdk bootstrap
```

---
## Deploy

Basic deployment (all defaults):
```
cdk deploy
```

Custom images / key pair example:
```
cdk deploy \
	--parameters InfraStack:KeyName="llave1.pem" \
	--parameters InfraStack:BackendImage="myrepo/backend:prod" \
	--parameters InfraStack:FrontendImage="myrepo/frontend:prod"
```

Key Outputs:
- FrontendAlbDns – Public DNS to open in browser (HTTP)
- BackendAlbDns – Internal DNS (resolves only inside VPC)
- BastionPublicIp – Use for SSH access
- BooksTableName – DynamoDB table name (`tb_books`)

---
## Verifying Deployment

1. Open the frontend in a browser:
	 `http://<FrontendAlbDns>`

2. (Optional) From the bastion or frontend instance, test backend health:
```
curl http://<BackendAlbDns>:5001/healthz
```
Expect HTTP 200.

3. Check that frontend API calls hit the backend ALB (network tab in browser dev tools, or app logs via SSH).

---
## SSH Access

SSH user for Ubuntu SSM parameter AMI is typically `ubuntu`.

1) Bastion:
```
ssh -i ~/.ssh/llave1.pem ubuntu@<BastionPublicIp>
```

2) From bastion to frontend/backend:
```
ssh ubuntu@<FrontendInstancePrivateIp>
ssh ubuntu@<BackendInstancePrivateIp>
```

ProxyCommand one-liner (from your local machine directly to backend):
```
ssh -i ~/.ssh/llave1.pem \
	-o ProxyCommand="ssh -i ~/.ssh/llave1.pem -W %h:%p ubuntu@<BastionPublicIp>" \
	ubuntu@<BackendInstancePrivateIp>
```

---
## Updating Containers

Current approach runs each container once via UserData. To deploy a new version:
- SSH to the instance, stop & remove container, pull new image, re-run `docker run ...`.
OR
- Re-deploy the stack with a new `BackendImage` / `FrontendImage` tag (will replace instance if changes force update).

Potential improvements (not implemented):
- Use ECS / Fargate or an Auto Scaling Group with Rolling updates
- Add HTTPS (ACM certificate + listener on 443)
- Restrict SSH ingress to your IP (replace 0.0.0.0/0 for SgBastion)

---
## DynamoDB Access Reminder

If your application fails with DynamoDB access errors, verify the imported role `LabRole` has the needed permissions (e.g., `dynamodb:PutItem`, `GetItem`, `Query`, `Scan`, `UpdateItem`, `DeleteItem` on the `tb_books` table). Add permissions outside this stack if required.

---
## Destroy

```
cdk destroy
```

Note: This removes the ALBs, EC2 instances, VPC, and the DynamoDB table (DATA LOSS). Export or backup required data first.

---
## Troubleshooting

Issue: Backend ALB creation fails with subnet/AZ error
Cause: Internal ALB requires at least 2 subnets across different AZs. Ensure region supports >=2 AZs and both private-back subnets were created.

Issue: AccessDenied (iam:PutRolePolicy) during deploy
Cause: Attempt to modify `LabRole`. We intentionally avoid granting table permissions here.

Issue: Frontend cannot reach backend
Checks:
- From frontend instance: `curl -v http://<BackendAlbDns>:5001/healthz`
- Confirm SgAlbFront ingress into SgAlbBack (port 5001) exists
- Confirm container still running: `docker ps`

---
## Change Log (Summary)

v2 (current): Dual ALBs, segregated private subnets (front/back), environment variable wiring, DynamoDB table.
v1 (legacy): Single bastion + two private instances (no ALBs, simpler SG model).

