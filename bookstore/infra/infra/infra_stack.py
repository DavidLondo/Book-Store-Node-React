import os
from aws_cdk import (
    Aws,
    Duration,
    RemovalPolicy,
    Stack,
    CfnOutput,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_autoscaling as autoscaling,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
)
from aws_cdk import aws_elasticloadbalancingv2_targets as elbv2_targets
from constructs import Construct


class InfraStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1) Networking: VPC with public and private subnets, 1 NAT GW
        vpc = ec2.Vpc(
            self,
            "BookstoreVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="private-egress",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # DynamoDB Gateway Endpoint to avoid NAT for table access
        vpc.add_gateway_endpoint(
            "DynamoDbEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)],
        )
        vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)],
        )

        # 2) Data: DynamoDB table
        table = dynamodb.Table(
            self,
            "BooksTable",
            table_name="tb_books",
            partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,  # keep data on stack delete
        )

        # 3) Security Groups
        alb_sg = ec2.SecurityGroup(self, "AlbSG", vpc=vpc, description="ALB SG", allow_all_outbound=True)
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "Allow HTTP from anywhere")

        backend_sg = ec2.SecurityGroup(self, "BackendSG", vpc=vpc, description="Backend SG", allow_all_outbound=True)
        backend_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(5001), "Allow ALB to hit backend on 5001")

        # 4) IAM: We'll use an existing role provided by the lab (LabRole) later in the Launch Template.

    # 5) EC2 Instances (git clone + build)
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            # Log bootstrap
            "set -euxo pipefail",
            "exec > >(tee -a /var/log/bookstore-bootstrap.log) 2>&1",
            "export DEBIAN_FRONTEND=noninteractive",
            "sudo apt-get update -y",
                "sudo apt-get install -y git curl unzip ca-certificates",
            # Node.js 20 (más reciente y soportado)
            "curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -",
            "sudo apt-get install -y nodejs",
            # Prep
            "sudo mkdir -p /opt/bookstore",
            "sudo chown ubuntu:ubuntu /opt/bookstore",
            "cd /opt/bookstore",
            # Código (repo público)
            "git clone --depth 1 --branch main https://github.com/DavidLondo/Book-Store-Node-React.git src",
            # Build frontend
            "cd /opt/bookstore/src/bookstore/frontend",
            "sudo -u ubuntu npm ci || sudo -u ubuntu npm install",
            "sudo -u ubuntu npm run build",
            # Backend env y deps
            "cd /opt/bookstore/src/bookstore/backend",
            "echo 'NODE_ENV=production' | sudo tee .env",
            "echo 'PORT=5001' | sudo tee -a .env",
            f"echo 'AWS_REGION={Aws.REGION}' | sudo tee -a .env",
            f"echo 'TABLE_NAME={table.table_name}' | sudo tee -a .env",
            "sudo -u ubuntu npm ci --omit=dev || sudo -u ubuntu npm install --omit=dev",
            # Seed best-effort
            "node seeder.js || true",
            # Servicio systemd
            "sudo tee /etc/systemd/system/bookstore.service > /dev/null << 'EOF'\n"
            "[Unit]\nDescription=Bookstore Backend Node Server\nAfter=network.target\n\n"
            "[Service]\nType=simple\nUser=ubuntu\nWorkingDirectory=/opt/bookstore/src/bookstore/backend\n"
            "EnvironmentFile=/opt/bookstore/src/bookstore/backend/.env\nExecStart=/usr/bin/node server.js\n"
            "Restart=always\nRestartSec=3\n\n[Install]\nWantedBy=multi-user.target\nEOF",
            "sudo systemctl daemon-reload",
            "sudo systemctl enable bookstore",
            "sudo systemctl start bookstore",
            # Espera a que responda /healthz
            "for i in $(seq 1 60); do curl -fsS http://127.0.0.1:5001/healthz && break || sleep 5; done || true",
            # Dump estado a logs
            "sudo systemctl status bookstore --no-pager || true",
            "journalctl -u bookstore -n 200 --no-pager || true",
        )

        # IMPORTANT: Use existing LabRole for instances; do not create/modify roles
        instance_role = iam.Role.from_role_name(self, "ExistingLabRole", role_name="LabRole")

        # Switch to Ubuntu 22.04 LTS via SSM Parameter
        ubuntu_ami = ec2.MachineImage.from_ssm_parameter(
            "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id",
            os=ec2.OperatingSystemType.LINUX,
        )

        # Create one instance per private-egress subnet (AZ)
        private_subnets = vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS).subnets
        instances = []
        for idx, subnet in enumerate(private_subnets):
            inst = ec2.Instance(
                self,
                f"BackendInstance{idx+1}",
                vpc=vpc,
                vpc_subnets=ec2.SubnetSelection(subnets=[subnet]),
                instance_type=ec2.InstanceType("t3.micro"),
                machine_image=ubuntu_ami,
                role=instance_role,
                security_group=backend_sg,
                user_data=user_data,
                key_name=None,
            )
            instances.append(inst)

        # 7) Load Balancer in public subnets
        alb = elbv2.ApplicationLoadBalancer(
            self,
            "BackendAlb",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_sg,
        )

        listener = alb.add_listener("HttpListener", port=80, open=True)
        target_group = listener.add_targets(
            "BackendTargets",
            port=5001,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[elbv2_targets.InstanceTarget(i) for i in instances],
            health_check=elbv2.HealthCheck(
                path="/healthz",
                port="5001",
                healthy_http_codes="200",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
        )

        # 8) Outputs (ALB-only setup)
        CfnOutput(self, "WebsiteURL", value=f"http://{alb.load_balancer_dns_name}", description="Frontend+API via ALB")
        CfnOutput(self, "AlbDNS", value=alb.load_balancer_dns_name, description="ALB DNS for API")
        CfnOutput(self, "DynamoTable", value=table.table_name)

