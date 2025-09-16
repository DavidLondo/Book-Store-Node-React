import os
from aws_cdk import (
    Aws,
    Duration,
    RemovalPolicy,
    Stack,
    CfnOutput,
    DockerImage,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_autoscaling as autoscaling,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3_deployment as s3deploy,
    aws_s3_assets as s3assets,
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

        # 4) IAM Role for EC2 instances
        instance_role = iam.Role(
            self,
            "BackendInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="EC2 role for backend instances to read DynamoDB and S3 assets",
        )
        # SSM access for troubleshooting (Session Manager)
        instance_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
        )
        # Allow read access to the DynamoDB table
        table.grant_read_data(instance_role)

        # 5) Backend code as S3 Asset (zip of backend/ directory)
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        backend_dir = os.path.join(repo_root, "backend")
        frontend_dir = os.path.join(repo_root, "frontend")

        backend_asset = s3assets.Asset(self, "BackendAsset", path=backend_dir)

        # 6) Launch Template + AutoScalingGroup
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            # Update OS and install deps
            "sudo dnf update -y || sudo yum update -y",
            "sudo dnf install -y git unzip awscli || sudo yum install -y git unzip awscli",
            # Install Node.js (Amazon Linux 2023 typically provides nodejs)
            "sudo dnf install -y nodejs || sudo yum install -y nodejs",
            # Prepare app directory
            "sudo mkdir -p /opt/bookstore",
            "sudo chown ec2-user:ec2-user /opt/bookstore",
            "cd /opt/bookstore",
            # Download backend asset from S3
            f"aws s3 cp {backend_asset.s3_object_url} /opt/bookstore/backend.zip",
            "unzip -o backend.zip -d /opt/bookstore/backend_src",
            # Some CDK assets zip the folder; detect nested folder (backend) and move
            "if [ -d /opt/bookstore/backend_src/backend ]; then mv /opt/bookstore/backend_src/backend /opt/bookstore/backend; else mv /opt/bookstore/backend_src /opt/bookstore/backend; fi",
            "cd /opt/bookstore/backend",
            # Create production .env
            f"echo 'NODE_ENV=production' | sudo tee .env",
            f"echo 'PORT=5001' | sudo tee -a .env",
            f"echo 'AWS_REGION={Aws.REGION}' | sudo tee -a .env",
            f"echo 'TABLE_NAME={table.table_name}' | sudo tee -a .env",
            # Install and build (backend has no build step; install deps)
            "npm ci --omit=dev || npm install --omit=dev",
            # Create systemd service
            "sudo bash -c 'cat > /etc/systemd/system/bookstore.service <<\EOF'",
            "[Unit]",
            "Description=Bookstore Backend Node Server",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            "User=ec2-user",
            "WorkingDirectory=/opt/bookstore/backend",
            "EnvironmentFile=/opt/bookstore/backend/.env",
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

    # Allow instances (instance role) to read the backend asset
    backend_asset.grant_read(instance_role)

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

        # 8) Frontend S3 bucket + CloudFront (SPA)
        site_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=False,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # CloudFront distribution with default S3 origin
        oai = cloudfront.OriginAccessIdentity(self, "OAI")
        site_bucket.grant_read(oai)

        cf_distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(site_bucket, origin_access_identity=oai),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            additional_behaviors={
                "api/*": cloudfront.BehaviorOptions(
                    origin=origins.LoadBalancerV2Origin(
                        alb,
                        protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
                        http_port=80,
                    ),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                )
            },
            error_responses=[
                cloudfront.ErrorResponse(http_status=403, response_http_status=200, response_page_path="/index.html", ttl=Duration.minutes(5)),
                cloudfront.ErrorResponse(http_status=404, response_http_status=200, response_page_path="/index.html", ttl=Duration.minutes(5)),
            ],
        )

        # 9) Deploy frontend (bundle React) into S3 using Docker node image
        s3deploy.BucketDeployment(
            self,
            "DeployFrontend",
            destination_bucket=site_bucket,
            distribution=cf_distribution,
            distribution_paths=["/*"],
            sources=[
                s3deploy.Source.asset(
                    path=frontend_dir,
                    bundling=s3deploy.BundlingOptions(
                        image=DockerImage.from_registry("node:20-alpine"),
                        command=[
                            "/bin/sh",
                            "-c",
                            # Install and build, copy build output to /asset-output
                            "(npm ci || npm install) && npm run build && cp -r build/* /asset-output/",
                        ],
                        # Increase timeout/build resources if needed
                        network=None,
                    ),
                )
            ],
        )

        # 10) Outputs
        CfnOutput(self, "CloudFrontURL", value=f"https://{cf_distribution.domain_name}", description="Frontend URL")
        CfnOutput(self, "AlbDNS", value=alb.load_balancer_dns_name, description="ALB DNS for API")
        CfnOutput(self, "DynamoTable", value=table.table_name)

