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

        # 5) Launch Template + AutoScalingGroup (git clone + build)
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            # Update OS and install deps
            "sudo dnf update -y || sudo yum update -y",
            "sudo dnf install -y git unzip awscli || sudo yum install -y git unzip awscli",
            # Install Node.js + npm (Amazon Linux 2023)
            "sudo dnf install -y nodejs npm || sudo yum install -y nodejs npm",
            # Prepare app directory
            "sudo mkdir -p /opt/bookstore",
            "sudo chown ec2-user:ec2-user /opt/bookstore",
            "cd /opt/bookstore",
            # Clone repository (public)
            "git clone --depth 1 --branch main https://github.com/DavidLondo/Book-Store-Node-React.git src",
            # Build frontend
            "cd /opt/bookstore/src/bookstore/frontend",
            "(npm ci || npm install)",
            "npm run build",
            # Setup backend
            "cd /opt/bookstore/src/bookstore/backend",
            # Create production .env
            f"echo 'NODE_ENV=production' | sudo tee .env",
            f"echo 'PORT=5001' | sudo tee -a .env",
            f"echo 'AWS_REGION={Aws.REGION}' | sudo tee -a .env",
            f"echo 'TABLE_NAME={table.table_name}' | sudo tee -a .env",
            # Install and build (backend has no build step; install deps)
            "npm ci --omit=dev || npm install --omit=dev",
            # Seed initial data (best-effort)
            "node seeder.js || true",
            # Create systemd service
            "sudo tee /etc/systemd/system/bookstore.service > /dev/null << 'EOF'",
            "[Unit]",
            "Description=Bookstore Backend Node Server",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            "User=ec2-user",
            "WorkingDirectory=/opt/bookstore/src/bookstore/backend",
            "EnvironmentFile=/opt/bookstore/src/bookstore/backend/.env",
            "ExecStart=/usr/bin/node server.js",
            "Restart=always",
            "RestartSec=3",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "EOF",
            # Start service
            "sudo systemctl daemon-reload",
            "sudo systemctl enable bookstore",
            "sudo systemctl start bookstore",
        )

        # IMPORTANT: Use existing LabRole for instances; do not create/modify roles
        instance_role = iam.Role.from_role_name(self, "ExistingLabRole", role_name="LabRole")

        lt = ec2.LaunchTemplate(
            self,
            "BackendLaunchTemplate",
            instance_type=ec2.InstanceType("t3.micro"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            role=instance_role,
            security_group=backend_sg,
            user_data=user_data,
        )

        asg = autoscaling.AutoScalingGroup(
            self,
            "BackendAsg",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            min_capacity=2,
            max_capacity=4,
            desired_capacity=2,
            launch_template=lt,
            health_check=autoscaling.HealthCheck.elb(grace=Duration.minutes(3)),
        )

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
            targets=[asg],
            health_check=elbv2.HealthCheck(
                path="/",
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

